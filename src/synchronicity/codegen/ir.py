"""Codegen intermediate representation: primitives and nested IR only.

Type shape for signatures is :class:`transformer_ir.TypeTransformerIR` (mirrors
runtime transformers but uses :class:`transformer_ir.ImplQualifiedRef` instead of
live implementation types). Materialize at emit time with
:func:`transformer_materialize.materialize_transformer_ir`.
"""

from __future__ import annotations

import dataclasses
import enum

from .transformer_ir import ImplQualifiedRef, TypeTransformerIR, WrapperRef


class MethodBindingKind(str, enum.Enum):
    """How an implementation method is bound on the class (mirrors ``classmethod`` / ``staticmethod``)."""

    INSTANCE = "instance"
    CLASSMETHOD = "classmethod"
    STATICMETHOD = "staticmethod"


@dataclasses.dataclass(frozen=True)
class TypeVarSpecIR:
    """Enough information to emit ``TypeVar`` / ``ParamSpec`` definitions.

    ``bound_translation_ir`` is set when the bound is a synchronized implementation class; it is the
    single source for how values typed as this type parameter translate at wrapper/impl boundaries.
    """

    name: str
    is_paramspec: bool
    constraint_parts: tuple[str, ...]
    bound_value: str | None
    covariant: bool
    contravariant: bool
    bound_translation_ir: TypeTransformerIR | None = None


@dataclasses.dataclass(frozen=True)
class ParameterIR:
    """One formal parameter: kind + optional type as :class:`TypeTransformerIR` (emit unwraps from this)."""

    name: str
    kind: int
    annotation_ir: TypeTransformerIR | None
    default_repr: str | None


@dataclasses.dataclass(frozen=True)
class SignatureIR:
    """Callable signature shape shared by overloads and concrete function/method implementations."""

    parameters: tuple[ParameterIR, ...]
    return_transformer_ir: TypeTransformerIR


@dataclasses.dataclass(frozen=True)
class ModuleCompilationIR:
    """Planned contents of one generated wrapper module (before any text emission)."""

    target_module: str
    synchronizer_name: str
    impl_modules: frozenset[str]
    cross_module_imports: dict[str, frozenset[str]]
    typevar_specs: tuple[TypeVarSpecIR, ...]
    class_wrappers: tuple[ClassWrapperIR, ...]
    module_functions_ir: tuple[ModuleLevelFunctionIR, ...]
    manual_reexports: tuple[ManualReexportIR, ...] = ()

    @property
    def has_wrapped_classes(self) -> bool:
        return bool(self.class_wrappers)

    @property
    def class_refs(self) -> tuple[ImplQualifiedRef, ...]:
        return tuple(c.impl_ref for c in self.class_wrappers)

    @property
    def function_refs(self) -> tuple[ImplQualifiedRef, ...]:
        return tuple(f.impl_ref for f in self.module_functions_ir)


@dataclasses.dataclass(frozen=True)
class ModuleLevelFunctionIR:
    """Parsed module-level function: parameters + return type as transformer IR."""

    impl_ref: ImplQualifiedRef
    needs_async_wrapper: bool
    is_async_gen: bool
    parameters: tuple[ParameterIR, ...]
    return_transformer_ir: TypeTransformerIR
    overloads: tuple[SignatureIR, ...] = ()


@dataclasses.dataclass(frozen=True)
class ManualReexportIR:
    """A module-level name that should be re-exported directly from the impl module."""

    impl_ref: ImplQualifiedRef
    export_name: str


@dataclasses.dataclass(frozen=True)
class MethodWrapperIR:
    """Parsed method: parameters + return type as transformer IR (owner context is separate)."""

    method_name: str
    method_type: MethodBindingKind
    parameters: tuple[ParameterIR, ...]
    is_async_gen: bool
    is_async: bool
    return_transformer_ir: TypeTransformerIR
    overloads: tuple[SignatureIR, ...] = ()


@dataclasses.dataclass(frozen=True)
class PropertyWrapperIR:
    """Parsed @property: name, getter return type, and optional setter value type."""

    name: str
    return_transformer_ir: TypeTransformerIR | None
    has_setter: bool
    setter_value_ir: TypeTransformerIR | None


class ManualClassAttributeAccessKind(str, enum.Enum):
    """How to reference a manual class attribute in emitted wrapper code."""

    ATTRIBUTE = "attribute"
    RAW_CLASS_DICT = "raw_class_dict"


@dataclasses.dataclass(frozen=True)
class ManualClassAttributeIR:
    """A class attribute that should be copied into the generated wrapper class unchanged."""

    name: str
    access_kind: ManualClassAttributeAccessKind


@dataclasses.dataclass(frozen=True)
class ClassWrapperIR:
    """Parsed class: everything needed to emit the wrapper without live ``type`` objects.

    The implementation identity is ``impl_ref`` (``__module__`` + ``__qualname__``). The generated
    wrapper module name is not stored here; emitters take it from :class:`ModuleCompilationIR` or the
    compile API.

    ``attributes`` holds public instance attribute names with :class:`transformer_ir.TypeTransformerIR`
    for each annotation (no pre-rendered wrapper type strings).

    ``methods`` includes public methods, ``__init__`` (when not ``object.__init__``), and async
    iterator protocol dunders (``__aiter__``, ``__anext__``). The emitter partitions by
    ``method_name`` (e.g. iterator dunders map to ``__iter__``/``__aiter__``, ``__next__``/``__anext__``).

    ``wrapped_bases`` lists implementation bases that participate in synchronicity
    inheritance, each carrying both the impl ref and the resolved wrapper location.
    ``generic_type_parameters`` holds ``TypeVar`` / ``ParamSpec`` **names** for the
    ``typing.Generic[...]`` base; the emitter formats that base string.
    """

    impl_ref: ImplQualifiedRef
    wrapper_ref: WrapperRef
    wrapped_bases: tuple[tuple[ImplQualifiedRef, WrapperRef], ...]
    generic_type_parameters: tuple[str, ...] | None
    attributes: tuple[tuple[str, TypeTransformerIR | None], ...]
    properties: tuple[PropertyWrapperIR, ...]
    methods: tuple[MethodWrapperIR, ...]
    manual_attributes: tuple[ManualClassAttributeIR, ...] = ()
