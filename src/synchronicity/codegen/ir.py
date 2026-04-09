"""Codegen intermediate representation: primitives and nested IR only.

Type shape for signatures is :class:`transformer_ir.TypeTransformerIR` (mirrors
runtime transformers but uses :class:`transformer_ir.ImplQualifiedRef` instead of
live implementation types). Materialize at emit time with
:func:`transformer_materialize.materialize_transformer_ir`.
"""

from __future__ import annotations

import dataclasses
import enum

from .transformer_ir import ImplQualifiedRef, TypeTransformerIR


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
class ModuleCompilationIR:
    """Planned contents of one generated wrapper module (before any text emission)."""

    target_module: str
    synchronizer_name: str
    impl_modules: frozenset[str]
    cross_module_imports: dict[str, frozenset[str]]
    typevar_specs: tuple[TypeVarSpecIR, ...]
    class_wrappers: tuple[ClassWrapperIR, ...]
    module_functions_ir: tuple[ModuleLevelFunctionIR, ...]

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


@dataclasses.dataclass(frozen=True)
class MethodWrapperIR:
    """Parsed method: parameters + return type as transformer IR (owner context is separate)."""

    method_name: str
    method_type: MethodBindingKind
    parameters: tuple[ParameterIR, ...]
    is_async_gen: bool
    is_async: bool
    return_transformer_ir: TypeTransformerIR


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

    ``wrapped_base_impl_refs`` lists implementation bases that participate in synchronicity
    inheritance (each maps to a wrapper at emit time via :class:`~sync_registry.SyncRegistry`).
    ``generic_type_parameters`` holds ``TypeVar`` / ``ParamSpec`` **names** for the
    ``typing.Generic[...]`` base; the emitter formats that base string.
    """

    impl_ref: ImplQualifiedRef
    wrapped_base_impl_refs: tuple[ImplQualifiedRef, ...]
    generic_type_parameters: tuple[str, ...] | None
    attributes: tuple[tuple[str, TypeTransformerIR | None], ...]
    methods: tuple[MethodWrapperIR, ...]
