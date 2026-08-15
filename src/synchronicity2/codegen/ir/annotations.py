"""Data-only IR for parsed Python annotations.

Wrapped implementation classes and ``Self`` owners are referenced by
``(module, qualname)``. Everything else composes structurally. Emission turns
these nodes into source-generation behavior with ``codegen_for_annotation``.
"""

from __future__ import annotations

import dataclasses
import typing

from .references import ImplementationRef, WrapperClassRef


class AnnotationIRNode:
    """Marker base for parsed annotation nodes."""


@dataclasses.dataclass(frozen=True)
class PlainAnnotationIR(AnnotationIRNode):
    """Non-wrapped annotation; ``signature_text`` is the type as it should appear in source."""

    signature_text: str
    import_modules: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class WrappedClassRefIR(AnnotationIRNode):
    """Registered wrapped class with resolved wrapper location."""

    impl: ImplementationRef
    wrapper: WrapperClassRef


@dataclasses.dataclass(frozen=True)
class Synchronicity1WrappedClassRefIR(AnnotationIRNode):
    """Class wrapped by the optional Synchronicity 1 compatibility synchronizer."""

    impl: ImplementationRef
    wrapper: WrapperClassRef


@dataclasses.dataclass(frozen=True)
class TypeVarRefIR(AnnotationIRNode):
    """Reference to a module-level ``typing.TypeVar`` by name.

    Bound translation behavior comes from :class:`~ir.TypeParameterIR`.
    """

    name: str


@dataclasses.dataclass(frozen=True)
class SelfAnnotationIR(AnnotationIRNode):
    """``typing.Self`` tied to a wrapped owner class."""

    owner_impl: ImplementationRef
    wrapper: WrapperClassRef


@dataclasses.dataclass(frozen=True)
class ListAnnotationIR(AnnotationIRNode):
    item_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class DictAnnotationIR(AnnotationIRNode):
    key_ir: AnnotationIR
    value_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class SequenceAnnotationIR(AnnotationIRNode):
    item_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class CollectionAnnotationIR(AnnotationIRNode):
    item_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class TupleAnnotationIR(AnnotationIRNode):
    """Fixed ``tuple[T1, T2]`` or variadic ``tuple[T, ...]`` (``variadic=True``, single element)."""

    element_irs: tuple[AnnotationIR, ...]
    variadic: bool


@dataclasses.dataclass(frozen=True)
class OptionalAnnotationIR(AnnotationIRNode):
    inner_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class UnionAnnotationIR(AnnotationIRNode):
    arm_irs: tuple[AnnotationIR, ...]
    source_label: str | None = None


@dataclasses.dataclass(frozen=True)
class AsyncGeneratorAnnotationIR(AnnotationIRNode):
    yield_annotation_ir: AnnotationIR
    send_type_str: str | None
    send_type_import_modules: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class SyncGeneratorAnnotationIR(AnnotationIRNode):
    yield_annotation_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class AsyncIteratorAnnotationIR(AnnotationIRNode):
    item_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class AsyncIterableAnnotationIR(AnnotationIRNode):
    item_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class CoroutineAnnotationIR(AnnotationIRNode):
    return_annotation_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class AwaitableAnnotationIR(AnnotationIRNode):
    inner_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class AsyncContextManagerAnnotationIR(AnnotationIRNode):
    value_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class CallableAnnotationIR(AnnotationIRNode):
    parameter_irs: tuple[AnnotationIR, ...] | None
    return_annotation_ir: AnnotationIR
    params_signature_text: str | None = None
    params_signature_import_modules: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class ParameterizedWrappedClassRefIR(AnnotationIRNode):
    """Wrapped class subscripted with type arguments, e.g. ``SomeContainer[WrappedType]``."""

    wrapped_class_ir: WrappedClassRefIR | Synchronicity1WrappedClassRefIR
    type_argument_irs: tuple[AnnotationIR, ...]


AnnotationIR = typing.Union[
    PlainAnnotationIR,
    WrappedClassRefIR,
    Synchronicity1WrappedClassRefIR,
    TypeVarRefIR,
    SelfAnnotationIR,
    ListAnnotationIR,
    DictAnnotationIR,
    SequenceAnnotationIR,
    CollectionAnnotationIR,
    TupleAnnotationIR,
    OptionalAnnotationIR,
    UnionAnnotationIR,
    AsyncGeneratorAnnotationIR,
    SyncGeneratorAnnotationIR,
    AsyncIteratorAnnotationIR,
    AsyncIterableAnnotationIR,
    CoroutineAnnotationIR,
    AwaitableAnnotationIR,
    AsyncContextManagerAnnotationIR,
    CallableAnnotationIR,
    ParameterizedWrappedClassRefIR,
]
