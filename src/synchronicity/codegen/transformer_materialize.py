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
    WrappedClassTypeIR,
)


def impl_qualified(t: type) -> ImplQualifiedRef:
    return ImplQualifiedRef(module=t.__module__, qualname=t.__qualname__)


def annotation_to_transformer_ir(
    annotation: object,
    sync: SyncRegistry,
    *,
    owner_impl_type: type | None = None,
    owner_has_type_parameters: bool = False,
) -> TypeTransformerIR:
    """Mirror :func:`type_transformer.create_transformer` but produce IR (qualified refs, no ``TypeTransformer``)."""
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
                ),
                annotation_to_transformer_ir(
                    args[1],
                    sync,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
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
                )
            )
        return AsyncIterableTypeIR(IdentityTypeIR(tt._format_annotation_str(typing.Any)))

    if origin is collections.abc.AsyncGenerator:
        if args:
            send_type_str = "None"
            if len(args) > 1:
                send_type_str = tt._format_annotation_str(args[1])
            return AsyncGeneratorTypeIR(
                annotation_to_transformer_ir(
                    args[0],
                    sync,
                    owner_impl_type=owner_impl_type,
                    owner_has_type_parameters=owner_has_type_parameters,
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
