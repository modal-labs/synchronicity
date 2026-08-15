"""Data-only IR for parsed Python annotations.

Wrapped implementation classes and ``Self`` owners are referenced by
``(module, qualname)``. Everything else composes structurally. Emission turns
these nodes into source-generation behavior with ``codegen_for_annotation``.
"""

from __future__ import annotations

import dataclasses

from .references import ObjectReferenceIR


class AnnotationIR:
    """Base class for parsed annotation IR nodes."""


@dataclasses.dataclass(frozen=True)
class PlainAnnotationIR(AnnotationIR):
    """Non-wrapped annotation; ``signature_text`` is the type as it should appear in source."""

    signature_text: str
    import_modules: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class WrappedClassRefIR(AnnotationIR):
    """Registered wrapped class with resolved wrapper location."""

    impl: ObjectReferenceIR
    wrapper: ObjectReferenceIR


@dataclasses.dataclass(frozen=True)
class Synchronicity1WrappedClassRefIR(AnnotationIR):
    """Class wrapped by the optional Synchronicity 1 compatibility synchronizer."""

    impl: ObjectReferenceIR
    wrapper: ObjectReferenceIR


@dataclasses.dataclass(frozen=True)
class TypeVarRefIR(AnnotationIR):
    """Reference to a module-level ``typing.TypeVar`` by name.

    Bound translation behavior comes from :class:`~ir.TypeParameterIR`.
    """

    name: str


@dataclasses.dataclass(frozen=True)
class SelfAnnotationIR(AnnotationIR):
    """``typing.Self`` tied to a wrapped owner class."""

    owner_impl: ObjectReferenceIR
    wrapper: ObjectReferenceIR


@dataclasses.dataclass(frozen=True)
class ListAnnotationIR(AnnotationIR):
    item_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class DictAnnotationIR(AnnotationIR):
    key_ir: AnnotationIR
    value_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class SequenceAnnotationIR(AnnotationIR):
    item_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class CollectionAnnotationIR(AnnotationIR):
    item_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class TupleAnnotationIR(AnnotationIR):
    """Fixed ``tuple[T1, T2]`` or variadic ``tuple[T, ...]`` (``variadic=True``, single element)."""

    element_irs: tuple[AnnotationIR, ...]
    variadic: bool


@dataclasses.dataclass(frozen=True)
class OptionalAnnotationIR(AnnotationIR):
    inner_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class UnionAnnotationIR(AnnotationIR):
    arm_irs: tuple[AnnotationIR, ...]
    source_label: str | None = None


@dataclasses.dataclass(frozen=True)
class AsyncGeneratorAnnotationIR(AnnotationIR):
    yield_annotation_ir: AnnotationIR
    send_type_str: str | None
    send_type_import_modules: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class SyncGeneratorAnnotationIR(AnnotationIR):
    yield_annotation_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class AsyncIteratorAnnotationIR(AnnotationIR):
    item_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class AsyncIterableAnnotationIR(AnnotationIR):
    item_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class CoroutineAnnotationIR(AnnotationIR):
    return_annotation_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class AwaitableAnnotationIR(AnnotationIR):
    inner_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class AsyncContextManagerAnnotationIR(AnnotationIR):
    value_ir: AnnotationIR


@dataclasses.dataclass(frozen=True)
class CallableAnnotationIR(AnnotationIR):
    parameter_irs: tuple[AnnotationIR, ...] | None
    return_annotation_ir: AnnotationIR
    params_signature_text: str | None = None
    params_signature_import_modules: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class ParameterizedWrappedClassRefIR(AnnotationIR):
    """Wrapped class subscripted with type arguments, e.g. ``SomeContainer[WrappedType]``."""

    wrapped_class_ir: WrappedClassRefIR | Synchronicity1WrappedClassRefIR
    type_argument_irs: tuple[AnnotationIR, ...]
