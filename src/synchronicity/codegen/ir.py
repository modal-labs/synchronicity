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


# Backward-compatible alias for “reference to impl object” in module plans.
ImplObjectRef = ImplQualifiedRef


@dataclasses.dataclass(frozen=True)
class TypeVarSpecIR:
    """Enough information to emit ``TypeVar`` / ``ParamSpec`` definitions."""

    name: str
    is_paramspec: bool
    constraint_parts: tuple[str, ...]
    bound_value: str | None
    covariant: bool
    contravariant: bool


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

    ``dunders`` holds implementation dunder methods keyed by **impl** name (e.g. ``__aiter__``,
    ``__anext__``). Those names are omitted from ``methods``. Async-iterator protocol dunders are the
    only entries today; the emitter maps ``__aiter__`` / ``__anext__`` to wrapper sync/async surface
    names (``__iter__``/``__aiter__``, ``__next__``/``__anext__``) from the key alone.
    """

    impl_ref: ImplQualifiedRef
    wrapped_base_names: tuple[str, ...]
    generic_base: str | None
    owner_has_type_parameters: bool
    attributes: tuple[tuple[str, str], ...]
    init_parameters: tuple[ParameterIR, ...]
    methods: tuple[MethodWrapperIR, ...]
    dunders: dict[str, MethodWrapperIR]
