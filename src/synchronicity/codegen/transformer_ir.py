"""IR mirroring :mod:`type_transformer` structure using qualified names, not live types.

Wrapped implementation classes and ``Self`` owners are referenced by
``(module, qualname)``. Everything else composes the same way as runtime
transformers. Emit time calls :func:`transformer_materialize.materialize_transformer_ir`.
"""

from __future__ import annotations

import dataclasses
import typing


@dataclasses.dataclass(frozen=True)
class ImplQualifiedRef:
    """``__module__`` + ``__qualname__`` of an implementation class (or type)."""

    module: str
    qualname: str


@dataclasses.dataclass(frozen=True)
class IdentityTypeIR:
    """Non-wrapped annotation; ``signature_text`` is the type as it should appear in source."""

    signature_text: str


@dataclasses.dataclass(frozen=True)
class WrappedClassTypeIR:
    """Registered wrapped class (``ImplQualifiedRef``; materialized with :class:`~sync_registry.SyncRegistry`)."""

    impl: ImplQualifiedRef


@dataclasses.dataclass(frozen=True)
class TypeVarIR:
    """Reference to a module-level ``typing.TypeVar`` by name (bound / translation from :class:`~ir.TypeVarSpecIR`)."""

    name: str


@dataclasses.dataclass(frozen=True)
class SelfTypeIR:
    """``typing.Self`` tied to a wrapped owner class."""

    owner_impl: ImplQualifiedRef


@dataclasses.dataclass(frozen=True)
class ListTypeIR:
    item: TypeTransformerIR


@dataclasses.dataclass(frozen=True)
class DictTypeIR:
    key: TypeTransformerIR
    value: TypeTransformerIR


@dataclasses.dataclass(frozen=True)
class TupleTypeIR:
    """Fixed ``tuple[T1, T2]`` or variadic ``tuple[T, ...]`` (``variadic=True``, single element)."""

    elements: tuple[TypeTransformerIR, ...]
    variadic: bool


@dataclasses.dataclass(frozen=True)
class OptionalTypeIR:
    inner: TypeTransformerIR


@dataclasses.dataclass(frozen=True)
class AsyncGeneratorTypeIR:
    yield_item: TypeTransformerIR
    send_type_str: str | None


@dataclasses.dataclass(frozen=True)
class SyncGeneratorTypeIR:
    yield_item: TypeTransformerIR


@dataclasses.dataclass(frozen=True)
class AsyncIteratorTypeIR:
    item: TypeTransformerIR


@dataclasses.dataclass(frozen=True)
class AsyncIterableTypeIR:
    item: TypeTransformerIR


@dataclasses.dataclass(frozen=True)
class CoroutineTypeIR:
    return_type: TypeTransformerIR


@dataclasses.dataclass(frozen=True)
class AwaitableTypeIR:
    inner: TypeTransformerIR


TypeTransformerIR = typing.Union[
    IdentityTypeIR,
    WrappedClassTypeIR,
    TypeVarIR,
    SelfTypeIR,
    ListTypeIR,
    DictTypeIR,
    TupleTypeIR,
    OptionalTypeIR,
    AsyncGeneratorTypeIR,
    SyncGeneratorTypeIR,
    AsyncIteratorTypeIR,
    AsyncIterableTypeIR,
    CoroutineTypeIR,
    AwaitableTypeIR,
]
