"""Function wrapper code generation."""

from __future__ import annotations

import types
import typing

from .emitters.sync_async_wrappers import emit_module_level_function
from .parse import parse_module_level_function_ir


def compile_function(
    f: types.FunctionType,
    target_module: str,
    synchronized_types: dict[type, tuple[str, str]],
    *,
    globals_dict: dict[str, typing.Any] | None = None,
    runtime_package: str = "synchronicity",
) -> str:
    """
    Compile a function into a wrapper that provides both sync and async versions.

    Args:
        f: The function to compile
        target_module: Target module where this function will be generated
        synchronized_types: Dict mapping impl types to (target_module, wrapper_name)
        globals_dict: Optional globals dict for resolving forward references

    Returns:
        String containing the generated async wrapper function and decorated sync function
    """
    ir = parse_module_level_function_ir(
        f,
        target_module,
        synchronized_types,
        globals_dict=globals_dict,
        runtime_package=runtime_package,
    )
    return emit_module_level_function(ir, synchronized_types, target_module)
