"""Codegen intermediate representation: primitives and nested IR only.

Type shape for signatures is :class:`transformer_ir.TypeTransformerIR` (mirrors
runtime transformers but uses :class:`transformer_ir.ImplQualifiedRef` instead of
live implementation types). Materialize at emit time with
:func:`transformer_materialize.materialize_transformer_ir`.
"""

from __future__ import annotations

import dataclasses

from .transformer_ir import ImplQualifiedRef, TypeTransformerIR

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
class ModuleCompilationIR:
    """Planned contents of one generated wrapper module (before any text emission)."""

    target_module: str
    synchronizer_name: str
    impl_modules: frozenset[str]
    has_wrapped_classes: bool
    cross_module_imports: dict[str, frozenset[str]]
    typevar_specs: tuple[TypeVarSpecIR, ...]
    class_refs: tuple[ImplQualifiedRef, ...]
    function_refs: tuple[ImplQualifiedRef, ...]
    class_wrappers: tuple[ClassWrapperIR, ...]
    module_functions_ir: tuple[ModuleLevelFunctionIR, ...]


@dataclasses.dataclass(frozen=True)
class ModuleLevelFunctionIR:
    """Parsed module-level function: binding strings + return type as transformer IR."""

    impl_ref: ImplQualifiedRef
    origin_module: str
    impl_name: str
    needs_async_wrapper: bool
    is_async_gen: bool
    param_str: str
    call_args_str: str
    unwrap_code: str
    return_transformer_ir: TypeTransformerIR


@dataclasses.dataclass(frozen=True)
class IteratorProtocolMethodIR:
    """Async iterator protocol bridge (__aiter__/__anext__ → sync/async surface)."""

    impl_method_name: str
    sync_method_name: str
    async_method_name: str
    call_expr: str
    return_transformer_ir: TypeTransformerIR
    use_async_def: bool
    stop_iteration_bridge: bool


@dataclasses.dataclass(frozen=True)
class ClassWrapperIR:
    """Parsed class: everything needed to emit the wrapper without live ``type`` objects."""

    impl_ref: ImplQualifiedRef
    wrapper_class_name: str
    origin_module: str
    current_target_module: str
    wrapped_base_names: tuple[str, ...]
    generic_base: str | None
    owner_has_type_parameters: bool
    attributes: tuple[tuple[str, str], ...]
    init_signature: str
    init_call: str
    init_unwrap_code: str
    methods: tuple[MethodWrapperIR, ...]
    iterator_methods: tuple[IteratorProtocolMethodIR, ...]


@dataclasses.dataclass(frozen=True)
class MethodWrapperIR:
    """Parsed method: binding strings + return type as transformer IR."""

    method_name: str
    method_type: str
    origin_module: str
    class_name: str
    current_target_module: str
    owner_impl_ref: ImplQualifiedRef
    owner_has_type_parameters: bool
    param_str: str
    call_args_str: str
    unwrap_code: str
    dummy_param_str: str
    is_async_gen: bool
    is_async: bool
    call_expr_prefix: str
    return_transformer_ir: TypeTransformerIR
