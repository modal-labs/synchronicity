"""Build :class:`transformer_ir.TypeTransformerIR` from live annotations and materialize to runtime transformers."""

from __future__ import annotations

import collections.abc
import inspect
import typing

from . import type_transformer as tt
from .sync_registry import SyncRegistry
from .transformer_ir import (
    AsyncGeneratorTypeIR,
    AsyncIterableTypeIR,
    AsyncIteratorTypeIR,
    AwaitableTypeIR,
    CoroutineTypeIR,
    DictTypeIR,
    IdentityTypeIR,
    ImplQualifiedRef,
    ListTypeIR,
    OptionalTypeIR,
    SelfTypeIR,
    SyncGeneratorTypeIR,
    TupleTypeIR,
    TypeTransformerIR,
    TypeVarWithBoundTypeIR,
    WrappedClassTypeIR,
)


def impl_qualified(t: type) -> ImplQualifiedRef:
    return ImplQualifiedRef(module=t.__module__, qualname=t.__qualname__)


def resolve_typevar_bound_to_wrapped_impl(
    tv: typing.TypeVar,
    sync: SyncRegistry,
    impl_modules: frozenset[str] | None,
) -> ImplQualifiedRef | None:
    """Return the impl ref when *tv*'s bound is a synchronized class or forward-refers to one by name."""
    bound = getattr(tv, "__bound__", None)
    if bound is None:
        return None
    if isinstance(bound, type):
        ref = impl_qualified(bound)
        return ref if ref in sync else None
    bound_name: str | None = None
    if hasattr(bound, "__forward_arg__"):
        bound_name = bound.__forward_arg__  # type: ignore[assignment]
    elif isinstance(bound, str):
        bound_name = bound
    if bound_name is None:
        return None
    for ref in sync:
        if ref.qualname.split(".")[-1] != bound_name:
            continue
        if impl_modules is not None and ref.module not in impl_modules:
            continue
        return ref
    return None


def annotation_to_transformer_ir(
    annotation: object,
    sync: SyncRegistry,
    *,
    owner_impl_type: type | None = None,
    owner_has_type_parameters: bool = False,
    impl_modules: frozenset[str] | None = None,
    generic_typevar_names: frozenset[str] | None = None,
) -> TypeTransformerIR:
    """Build :class:`transformer_ir.TypeTransformerIR` from a resolved annotation (no runtime transformers)."""
    if annotation == inspect.Signature.empty:
        return IdentityTypeIR("")
    if annotation is None:
        return IdentityTypeIR(tt._format_annotation_str(None))

    if hasattr(annotation, "__forward_arg__"):
        forward_str = annotation.__forward_arg__  # type: ignore
        raise TypeError(
            f"Found unresolved forward reference '{forward_str}' in type annotation. "
            f"Use inspect.get_annotations(eval_str=True) to resolve forward references."
        )

    if isinstance(annotation, type) and sync.has_wrapped_class(annotation):
        return WrappedClassTypeIR(impl_qualified(annotation))

    if isinstance(annotation, typing.TypeVar):
        bound_ref = resolve_typevar_bound_to_wrapped_impl(annotation, sync, impl_modules)
        if bound_ref is not None:
            skip_wrapped_bound = (
                generic_typevar_names is not None
                and annotation.__name__ in generic_typevar_names
                and owner_has_type_parameters
            )
            if not skip_wrapped_bound:
                return TypeVarWithBoundTypeIR(name=annotation.__name__, bound_impl=bound_ref)

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is None:
        if (
            tt._is_self_annotation(annotation)
            and owner_impl_type is not None
            and sync.has_wrapped_class(owner_impl_type)
        ):
            return SelfTypeIR(impl_qualified(owner_impl_type))
        return IdentityTypeIR(tt._format_annotation_str(annotation))

    if origin is list:
        if args:
            return ListTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    sync,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    generic_typevar_names=generic_typevar_names,
                )
            )
        return IdentityTypeIR(tt._format_annotation_str(annotation))

    if origin is dict:
        if len(args) >= 2:
            return DictTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    sync,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    generic_typevar_names=generic_typevar_names,
                ),
                annotation_to_transformer_ir(
                    args[1],
                    sync,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    generic_typevar_names=generic_typevar_names,
                ),
            )
        return IdentityTypeIR(tt._format_annotation_str(annotation))

    if origin is tuple:
        if args:
            if Ellipsis in args:
                return TupleTypeIR(
                    (
                        annotation_to_transformer_ir(
                            args[0],
                            sync,
                            owner_impl_type=owner_impl_type,
                            owner_has_type_parameters=owner_has_type_parameters,
                            impl_modules=impl_modules,
                            generic_typevar_names=generic_typevar_names,
                        ),
                    ),
                    variadic=True,
                )
            return TupleTypeIR(
                tuple(
                    annotation_to_transformer_ir(
                        arg,
                        sync,
                        owner_impl_type=owner_impl_type,
                        owner_has_type_parameters=owner_has_type_parameters,
                        impl_modules=impl_modules,
                        generic_typevar_names=generic_typevar_names,
                    )
                    for arg in args
                ),
                variadic=False,
            )
        return IdentityTypeIR(tt._format_annotation_str(annotation))

    if origin is typing.Union:
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1 and type(None) in args:
            return OptionalTypeIR(
                annotation_to_transformer_ir(
                    non_none_args[0],
                    sync,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    generic_typevar_names=generic_typevar_names,
                )
            )
        return IdentityTypeIR(tt._format_annotation_str(annotation))

    if origin is collections.abc.Generator or origin is collections.abc.Iterator:
        if args:
            return SyncGeneratorTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    sync,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    generic_typevar_names=generic_typevar_names,
                )
            )
        return IdentityTypeIR(tt._format_annotation_str(annotation))

    if origin is collections.abc.AsyncIterator:
        if args:
            return AsyncIteratorTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    sync,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    generic_typevar_names=generic_typevar_names,
                )
            )
        return AsyncIteratorTypeIR(IdentityTypeIR(tt._format_annotation_str(typing.Any)))

    if origin is collections.abc.AsyncIterable:
        if args:
            return AsyncIterableTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    sync,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    generic_typevar_names=generic_typevar_names,
                )
            )
        return AsyncIterableTypeIR(IdentityTypeIR(tt._format_annotation_str(typing.Any)))

    if origin is collections.abc.AsyncGenerator:
        if len(args) >= 1:
            send_type_str = "None"
            if len(args) > 1:
                send_type_str = tt._format_annotation_str(args[1])
            yield_arg = args[0]
            return AsyncGeneratorTypeIR(
                annotation_to_transformer_ir(
                    yield_arg,
                    sync,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    generic_typevar_names=generic_typevar_names,
                ),
                send_type_str=send_type_str,
            )
        return IdentityTypeIR(tt._format_annotation_str(annotation))

    if origin is collections.abc.Coroutine:
        if args and len(args) >= 3:
            return CoroutineTypeIR(
                annotation_to_transformer_ir(
                    args[2],
                    sync,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    generic_typevar_names=generic_typevar_names,
                )
            )
        return CoroutineTypeIR(IdentityTypeIR(tt._format_annotation_str(typing.Any)))

    if origin is collections.abc.Awaitable:
        if args:
            return AwaitableTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    sync,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
                    impl_modules=impl_modules,
                    generic_typevar_names=generic_typevar_names,
                )
            )
        return AwaitableTypeIR(IdentityTypeIR(tt._format_annotation_str(typing.Any)))

    return IdentityTypeIR(tt._format_annotation_str(annotation))


def materialize_transformer_ir(
    ir: TypeTransformerIR,
    sync: SyncRegistry,
    runtime_package: str,
) -> tt.TypeTransformer:
    if isinstance(ir, IdentityTypeIR):
        return tt.IdentityStrTransformer(ir.signature_text)
    if isinstance(ir, WrappedClassTypeIR):
        return tt.WrappedClassTransformer(ir.impl)
    if isinstance(ir, TypeVarWithBoundTypeIR):
        return tt.TypeVarBoundTransformer(ir.name, ir.bound_impl)
    if isinstance(ir, SelfTypeIR):
        return tt.SelfTransformer(ir.owner_impl)
    if isinstance(ir, ListTypeIR):
        return tt.ListTransformer(materialize_transformer_ir(ir.item, sync, runtime_package))
    if isinstance(ir, DictTypeIR):
        return tt.DictTransformer(
            materialize_transformer_ir(ir.key, sync, runtime_package),
            materialize_transformer_ir(ir.value, sync, runtime_package),
        )
    if isinstance(ir, TupleTypeIR):
        if ir.variadic:
            (single,) = ir.elements
            return tt.TupleTransformer([materialize_transformer_ir(single, sync, runtime_package)])
        return tt.TupleTransformer([materialize_transformer_ir(e, sync, runtime_package) for e in ir.elements])
    if isinstance(ir, OptionalTypeIR):
        return tt.OptionalTransformer(materialize_transformer_ir(ir.inner, sync, runtime_package))
    if isinstance(ir, AsyncGeneratorTypeIR):
        return tt.AsyncGeneratorTransformer(
            materialize_transformer_ir(ir.yield_item, sync, runtime_package),
            send_type_str=ir.send_type_str,
        )
    if isinstance(ir, SyncGeneratorTypeIR):
        return tt.SyncGeneratorTransformer(materialize_transformer_ir(ir.yield_item, sync, runtime_package))
    if isinstance(ir, AsyncIteratorTypeIR):
        return tt.AsyncIteratorTransformer(
            materialize_transformer_ir(ir.item, sync, runtime_package),
            runtime_package,
        )
    if isinstance(ir, AsyncIterableTypeIR):
        return tt.AsyncIterableTransformer(
            materialize_transformer_ir(ir.item, sync, runtime_package),
            runtime_package,
        )
    if isinstance(ir, CoroutineTypeIR):
        return tt.CoroutineTransformer(materialize_transformer_ir(ir.return_type, sync, runtime_package))
    if isinstance(ir, AwaitableTypeIR):
        return tt.AwaitableTransformer(materialize_transformer_ir(ir.inner, sync, runtime_package))
    raise TypeError(f"Unhandled transformer IR: {type(ir)!r}")
