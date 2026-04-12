"""Class and method wrapper code generation."""

from __future__ import annotations

import types
import typing

from .emitters.sync_async_wrappers import MethodEmitOwner, emit_class_from_ir, emit_method_wrapper_pair
from .ir import MethodBindingKind
from .parse import parse_class_wrapper_ir, parse_method_wrapper_ir
from .transformer_ir import ImplQualifiedRef


def compile_method_wrapper(
    method: types.FunctionType,
    method_name: str,
    current_target_module: str,
    impl_class: type,
    *,
    owner_has_type_parameters: bool = False,
    method_type: MethodBindingKind = MethodBindingKind.INSTANCE,
    globals_dict: dict[str, typing.Any] | None = None,
    generic_typevars: dict[str, typing.TypeVar | typing.ParamSpec] | None = None,
    runtime_package: str = "synchronicity",
) -> tuple[str, str]:
    """
    Compile a method wrapper class that provides both sync and async versions.
    """
    ir = parse_method_wrapper_ir(
        method,
        method_name,
        impl_class,
        owner_has_type_parameters=owner_has_type_parameters,
        method_type=method_type,
        globals_dict=globals_dict,
        generic_typevars=generic_typevars,
        impl_modules=frozenset({impl_class.__module__}),
    )
    owner = MethodEmitOwner(
        impl_ref=ImplQualifiedRef(impl_class.__module__, impl_class.__qualname__),
        target_module=current_target_module,
    )
    return emit_method_wrapper_pair(owner, ir, runtime_package=runtime_package)


def compile_class(
    cls: type,
    target_module: str,
    *,
    globals_dict: dict[str, typing.Any] | None = None,
    runtime_package: str = "synchronicity",
) -> str:
    """
    Compile a class into a wrapper class where all methods are wrapped.
    """
    ir = parse_class_wrapper_ir(
        cls,
        target_module,
        globals_dict=globals_dict,
        runtime_package=runtime_package,
        impl_modules=frozenset({cls.__module__}),
    )
    return emit_class_from_ir(ir, target_module, runtime_package=runtime_package)
