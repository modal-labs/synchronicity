"""Build :class:`transformer_ir.TypeTransformerIR` from live annotations and materialize to runtime transformers."""

from __future__ import annotations

import collections.abc
import contextlib
import dataclasses
import inspect
import types
import typing
import warnings

from synchronicity2.module import (
    _direct_wrapper_location,
    _inherited_wrapper_location,
)

from . import type_transformer as tt
from .ir import TypeVarSpecIR
from .transformer_ir import (
    AsyncContextManagerTypeIR,
    AsyncGeneratorTypeIR,
    AsyncIterableTypeIR,
    AsyncIteratorTypeIR,
    AwaitableTypeIR,
    CallableTypeIR,
    CoroutineTypeIR,
    DictTypeIR,
    IdentityTypeIR,
    ImplQualifiedRef,
    ListTypeIR,
    OptionalTypeIR,
    SelfTypeIR,
    SequenceTypeIR,
    SubscriptedWrappedClassTypeIR,
    SyncGeneratorTypeIR,
    TupleTypeIR,
    TypeTransformerIR,
    TypeVarIR,
    UnionTypeIR,
    WrappedClassTypeIR,
    WrapperRef,
)


@dataclasses.dataclass
class MaterializeContext:
    """Module-level type variable specs for resolving :class:`TypeVarIR` (name → bound translation)."""

    typevar_specs_by_name: dict[str, TypeVarSpecIR] | None = None


def impl_qualified(t: type) -> ImplQualifiedRef:
    return ImplQualifiedRef(module=t.__module__, qualname=t.__qualname__)


def _get_wrapper_location(impl_type: type) -> tuple[str, str] | None:
    """Read the wrapper location from the marker attribute set by ``Module.wrap_class``."""
    return _direct_wrapper_location(impl_type)


def _is_wrapped_impl(t: type) -> bool:
    return _direct_wrapper_location(t) is not None


def _warn_if_inherited_wrapper_reference(annotation: object, source_label: str | None) -> None:
    if not isinstance(annotation, type):
        return
    inherited = _inherited_wrapper_location(annotation)
    if inherited is None:
        return
    base, _location = inherited
    prefix = f"{source_label}: " if source_label else ""
    warnings.warn(
        prefix
        + "type annotation references subclass "
        + f"{annotation.__module__}.{annotation.__qualname__} of wrapped implementation class "
        + f"{base.__module__}.{base.__qualname__}, but the subclass is not directly wrapped; "
        + "treating it as an unwrapped identity type",
        UserWarning,
        stacklevel=3,
    )


def _wrapper_ref_from_type(impl_type: type) -> WrapperRef:
    loc = _get_wrapper_location(impl_type)
    assert loc is not None
    return WrapperRef(*loc)


def resolve_typevar_bound_to_wrapped_impl(
    tv: typing.TypeVar,
    known_impl_types: frozenset[type],
    impl_modules: frozenset[str] | None,
) -> ImplQualifiedRef | None:
    """Return the impl ref when *tv*'s bound is a synchronized class or forward-refers to one by name."""
    bound = getattr(tv, "__bound__", None)
    if bound is None:
        return None
    if isinstance(bound, type):
        if _is_wrapped_impl(bound):
            return impl_qualified(bound)
        return None
    bound_name: str | None = None
    if hasattr(bound, "__forward_arg__"):
        bound_name = bound.__forward_arg__  # type: ignore[assignment]
    elif isinstance(bound, str):
        bound_name = bound
    if bound_name is None:
        return None
    for t in known_impl_types:
        ref = impl_qualified(t)
        if ref.qualname.split(".")[-1] != bound_name:
            continue
        if impl_modules is not None and ref.module not in impl_modules:
            continue
        return ref
    return None


def annotation_import_modules(annotation: object) -> frozenset[str]:
    """Return non-builtin modules that the emitted annotation text will reference."""
    if annotation in (inspect.Signature.empty, None, type(None)):
        return frozenset()
    if isinstance(annotation, (typing.TypeVar, typing.ParamSpec)):
        return frozenset()
    if isinstance(annotation, list):
        modules: set[str] = set()
        for item in annotation:
            modules.update(annotation_import_modules(item))
        return frozenset(modules)

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    modules: set[str] = set()

    if origin is not None:
        origin_module = getattr(origin, "__module__", None)
        if isinstance(origin, type) and origin_module not in (
            None,
            "builtins",
            "__builtin__",
            "typing",
            "collections.abc",
        ):
            modules.add(origin_module)
        for arg in args:
            modules.update(annotation_import_modules(arg))
        return frozenset(modules)

    if isinstance(annotation, type):
        annotation_module = getattr(annotation, "__module__", None)
        if annotation_module not in (None, "builtins", "__builtin__", "typing"):
            modules.add(annotation_module)

    return frozenset(modules)


def _identity_ir_from_annotation(annotation: object) -> IdentityTypeIR:
    return IdentityTypeIR(
        signature_text=tt._format_annotation_str(annotation),
        import_modules=tuple(sorted(annotation_import_modules(annotation))),
    )


def annotation_to_transformer_ir(
    annotation: object,
    *,
    owner_impl_type: type | None = None,
    owner_has_type_parameters: bool = False,
    impl_modules: frozenset[str] | None = None,
    source_label: str | None = None,
) -> TypeTransformerIR:
    """Build :class:`transformer_ir.TypeTransformerIR` from a resolved annotation (no runtime transformers)."""
    if annotation == inspect.Signature.empty:
        return IdentityTypeIR("")
    if annotation is None:
        return _identity_ir_from_annotation(None)

    if hasattr(annotation, "__forward_arg__"):
        forward_str = annotation.__forward_arg__  # type: ignore
        raise TypeError(
            f"Found unresolved forward reference '{forward_str}' in type annotation. "
            f"Use inspect.get_annotations(eval_str=True) to resolve forward references."
        )

    _warn_if_inherited_wrapper_reference(annotation, source_label)

    if isinstance(annotation, type) and _is_wrapped_impl(annotation):
        return WrappedClassTypeIR(impl_qualified(annotation), _wrapper_ref_from_type(annotation))

    if isinstance(annotation, typing.TypeVar):
        return TypeVarIR(name=annotation.__name__)

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is None:
        if tt._is_self_annotation(annotation) and owner_impl_type is not None and _is_wrapped_impl(owner_impl_type):
            return SelfTypeIR(impl_qualified(owner_impl_type), _wrapper_ref_from_type(owner_impl_type))
        return _identity_ir_from_annotation(annotation)

    if origin is list:
        if args:
            return ListTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    source_label=source_label,
                )
            )
        return _identity_ir_from_annotation(annotation)

    if origin is dict:
        if len(args) >= 2:
            return DictTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    source_label=source_label,
                ),
                annotation_to_transformer_ir(
                    args[1],
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    source_label=source_label,
                ),
            )
        return _identity_ir_from_annotation(annotation)

    if origin is collections.abc.Sequence:
        if args:
            return SequenceTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    source_label=source_label,
                )
            )
        return _identity_ir_from_annotation(annotation)

    if origin is tuple:
        if args:
            if Ellipsis in args:
                return TupleTypeIR(
                    (
                        annotation_to_transformer_ir(
                            args[0],
                            owner_impl_type=owner_impl_type,
                            owner_has_type_parameters=owner_has_type_parameters,
                            impl_modules=impl_modules,
                            source_label=source_label,
                        ),
                    ),
                    variadic=True,
                )
            return TupleTypeIR(
                tuple(
                    annotation_to_transformer_ir(
                        arg,
                        owner_impl_type=owner_impl_type,
                        owner_has_type_parameters=owner_has_type_parameters,
                        impl_modules=impl_modules,
                        source_label=source_label,
                    )
                    for arg in args
                ),
                variadic=False,
            )
        return _identity_ir_from_annotation(annotation)

    if origin in (typing.Union, types.UnionType):
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1 and type(None) in args:
            return OptionalTypeIR(
                annotation_to_transformer_ir(
                    non_none_args[0],
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    source_label=source_label,
                )
            )
        return UnionTypeIR(
            tuple(
                annotation_to_transformer_ir(
                    arg,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    source_label=source_label,
                )
                for arg in args
            ),
            source_label=source_label,
        )

    if origin is collections.abc.Generator or origin is collections.abc.Iterator:
        if args:
            return SyncGeneratorTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    source_label=source_label,
                )
            )
        return _identity_ir_from_annotation(annotation)

    if origin is collections.abc.AsyncIterator:
        if args:
            return AsyncIteratorTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    source_label=source_label,
                )
            )
        return AsyncIteratorTypeIR(_identity_ir_from_annotation(typing.Any))

    if origin is collections.abc.AsyncIterable:
        if args:
            return AsyncIterableTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    source_label=source_label,
                )
            )
        return AsyncIterableTypeIR(_identity_ir_from_annotation(typing.Any))

    if origin is collections.abc.AsyncGenerator:
        if len(args) >= 1:
            send_type_str = "None"
            send_type_import_modules: tuple[str, ...] = ()
            if len(args) > 1:
                send_type_str = tt._format_annotation_str(args[1])
                send_type_import_modules = tuple(sorted(annotation_import_modules(args[1])))
            yield_arg = args[0]
            return AsyncGeneratorTypeIR(
                annotation_to_transformer_ir(
                    yield_arg,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    source_label=source_label,
                ),
                send_type_str=send_type_str,
                send_type_import_modules=send_type_import_modules,
            )
        return _identity_ir_from_annotation(annotation)

    if origin is collections.abc.Coroutine:
        if args and len(args) >= 3:
            return CoroutineTypeIR(
                annotation_to_transformer_ir(
                    args[2],
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    source_label=source_label,
                )
            )
        return CoroutineTypeIR(_identity_ir_from_annotation(typing.Any))

    if origin is collections.abc.Awaitable:
        if args:
            return AwaitableTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    source_label=source_label,
                )
            )
        return AwaitableTypeIR(_identity_ir_from_annotation(typing.Any))

    if origin is contextlib.AbstractAsyncContextManager:
        if args:
            return AsyncContextManagerTypeIR(
                value=annotation_to_transformer_ir(
                    args[0],
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    source_label=source_label,
                )
            )
        return AsyncContextManagerTypeIR(value=_identity_ir_from_annotation(typing.Any))

    if origin is collections.abc.Callable:
        if len(args) >= 2:
            params = args[0]
            return_type = annotation_to_transformer_ir(
                args[1],
                owner_impl_type=owner_impl_type,
                owner_has_type_parameters=owner_has_type_parameters,
                impl_modules=impl_modules,
                source_label=source_label,
            )
            if params is Ellipsis:
                return CallableTypeIR(None, return_type)
            if isinstance(params, list | tuple):
                return CallableTypeIR(
                    tuple(
                        annotation_to_transformer_ir(
                            param,
                            owner_impl_type=owner_impl_type,
                            owner_has_type_parameters=owner_has_type_parameters,
                            impl_modules=impl_modules,
                            source_label=source_label,
                        )
                        for param in params
                    ),
                    return_type,
                )
            params_identity_ir = _identity_ir_from_annotation(params)
            return CallableTypeIR(
                None,
                return_type,
                params_signature_text=params_identity_ir.signature_text,
                params_signature_import_modules=params_identity_ir.import_modules,
            )
        return _identity_ir_from_annotation(annotation)

    # Subscripted wrapped class, e.g. SomeContainer[WrappedType]
    if isinstance(origin, type) and _is_wrapped_impl(origin) and args:
        arg_irs = tuple(
            annotation_to_transformer_ir(
                arg,
                owner_impl_type=owner_impl_type,
                owner_has_type_parameters=owner_has_type_parameters,
                impl_modules=impl_modules,
                source_label=source_label,
            )
            for arg in args
        )
        return SubscriptedWrappedClassTypeIR(impl_qualified(origin), _wrapper_ref_from_type(origin), arg_irs)

    return _identity_ir_from_annotation(annotation)


def _materialize_typevar_ir(
    ir: TypeVarIR,
    runtime_package: str,
    ctx: MaterializeContext | None,
) -> tt.TypeTransformer:
    if ctx is None or ctx.typevar_specs_by_name is None:
        return tt.IdentityStrTransformer(ir.name)
    spec = ctx.typevar_specs_by_name.get(ir.name)
    if spec is None or spec.is_paramspec:
        return tt.IdentityStrTransformer(ir.name)
    if spec.bound_translation_ir is not None:
        inner = materialize_transformer_ir(spec.bound_translation_ir, runtime_package, ctx=ctx)
        return tt.TypeVarBoundTransformer(ir.name, inner)
    return tt.IdentityStrTransformer(ir.name)


def materialize_transformer_ir(
    ir: TypeTransformerIR,
    runtime_package: str,
    *,
    ctx: MaterializeContext | None = None,
) -> tt.TypeTransformer:
    if isinstance(ir, IdentityTypeIR):
        return tt.IdentityStrTransformer(ir.signature_text)
    if isinstance(ir, WrappedClassTypeIR):
        return tt.WrappedClassTransformer(ir.impl, ir.wrapper)
    if isinstance(ir, TypeVarIR):
        return _materialize_typevar_ir(ir, runtime_package, ctx)
    if isinstance(ir, SelfTypeIR):
        return tt.SelfTransformer(ir.owner_impl, ir.wrapper)
    if isinstance(ir, ListTypeIR):
        return tt.ListTransformer(materialize_transformer_ir(ir.item, runtime_package, ctx=ctx))
    if isinstance(ir, DictTypeIR):
        return tt.DictTransformer(
            materialize_transformer_ir(ir.key, runtime_package, ctx=ctx),
            materialize_transformer_ir(ir.value, runtime_package, ctx=ctx),
        )
    if isinstance(ir, SequenceTypeIR):
        return tt.SequenceTransformer(materialize_transformer_ir(ir.item, runtime_package, ctx=ctx))
    if isinstance(ir, TupleTypeIR):
        if ir.variadic:
            (single,) = ir.elements
            return tt.TupleTransformer([materialize_transformer_ir(single, runtime_package, ctx=ctx)])
        return tt.TupleTransformer([materialize_transformer_ir(e, runtime_package, ctx=ctx) for e in ir.elements])
    if isinstance(ir, OptionalTypeIR):
        return tt.OptionalTransformer(materialize_transformer_ir(ir.inner, runtime_package, ctx=ctx))
    if isinstance(ir, UnionTypeIR):
        return tt.UnionTransformer(
            [materialize_transformer_ir(item, runtime_package, ctx=ctx) for item in ir.items],
            source_label=ir.source_label,
        )
    if isinstance(ir, AsyncGeneratorTypeIR):
        return tt.AsyncGeneratorTransformer(
            materialize_transformer_ir(ir.yield_item, runtime_package, ctx=ctx),
            send_type_str=ir.send_type_str,
        )
    if isinstance(ir, SyncGeneratorTypeIR):
        return tt.SyncGeneratorTransformer(materialize_transformer_ir(ir.yield_item, runtime_package, ctx=ctx))
    if isinstance(ir, AsyncIteratorTypeIR):
        return tt.AsyncIteratorTransformer(
            materialize_transformer_ir(ir.item, runtime_package, ctx=ctx),
            runtime_package,
        )
    if isinstance(ir, AsyncIterableTypeIR):
        return tt.AsyncIterableTransformer(
            materialize_transformer_ir(ir.item, runtime_package, ctx=ctx),
            runtime_package,
        )
    if isinstance(ir, CoroutineTypeIR):
        return tt.CoroutineTransformer(materialize_transformer_ir(ir.return_type, runtime_package, ctx=ctx))
    if isinstance(ir, AwaitableTypeIR):
        return tt.AwaitableTransformer(materialize_transformer_ir(ir.inner, runtime_package, ctx=ctx))
    if isinstance(ir, CallableTypeIR):
        params = (
            None
            if ir.params is None
            else tuple(materialize_transformer_ir(param, runtime_package, ctx=ctx) for param in ir.params)
        )
        return tt.CallableTransformer(
            params,
            materialize_transformer_ir(ir.return_type, runtime_package, ctx=ctx),
            param_signature_text=ir.params_signature_text,
        )
    if isinstance(ir, SubscriptedWrappedClassTypeIR):
        arg_transformers = [materialize_transformer_ir(a, runtime_package, ctx=ctx) for a in ir.type_args]
        return tt.SubscriptedWrappedClassTransformer(ir.impl, ir.wrapper, arg_transformers)
    if isinstance(ir, AsyncContextManagerTypeIR):
        return tt.AsyncContextManagerTransformer(
            materialize_transformer_ir(ir.value, runtime_package, ctx=ctx),
            runtime_package,
        )
    raise TypeError(f"Unhandled transformer IR: {type(ir)!r}")
