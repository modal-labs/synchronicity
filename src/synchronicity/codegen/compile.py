"""Main compilation module for generating wrapper code.

Pipeline:
1. :func:`~synchronicity.codegen.registry.collect_synchronized_types` — aggregate class registrations
2. :func:`~synchronicity.codegen.parse.build_module_compilation_ir` — parse layout, cross-refs, typevars
3. :class:`~synchronicity.codegen.emitters.sync_async_wrappers.SyncAsyncWrapperEmitter` — emit source

Function- and method-level parsing lives in :mod:`synchronicity.codegen.parse`; the default sync/async
shape is emitted from :mod:`synchronicity.codegen.emitters.sync_async_wrappers`.
"""

from __future__ import annotations

from synchronicity.module import Module

from .compile_class import compile_class
from .compile_function import compile_function
from .emitters.protocol import CodegenEmitter
from .emitters.sync_async_wrappers import SyncAsyncWrapperEmitter
from .parse import build_module_compilation_ir
from .registry import collect_synchronized_types

__all__ = [
    "compile_class",
    "compile_function",
    "compile_module",
    "compile_modules",
    "collect_synchronized_types",
]


def compile_module(
    module: Module,
    synchronized_types: dict[type, tuple[str, str]],
    *,
    runtime_package: str = "synchronicity",
    emitter: CodegenEmitter | None = None,
) -> str:
    """
    Compile wrapped items for a single target module.

    Args:
        module: The Module instance with registered items
        synchronized_types: Dict mapping all implementation types to (target_module, wrapper_name)
        runtime_package: Dotted import path for runtime submodules in generated imports
        emitter: Optional emitter (defaults to :class:`SyncAsyncWrapperEmitter` with ``runtime_package``)

    Returns:
        String containing compiled wrapper code for this module
    """
    ir = build_module_compilation_ir(module, synchronized_types)
    gen = emitter or SyncAsyncWrapperEmitter(runtime_package=runtime_package)
    return gen.emit_module(ir, synchronized_types, registration_module=module)


def compile_modules(
    modules: list[Module],
    *,
    runtime_package: str = "synchronicity",
    emitter: CodegenEmitter | None = None,
) -> dict[str, str]:
    """
    Compile wrapped items into separate module files.

    Args:
        modules: List of Module instances to compile
        runtime_package: Dotted import path for runtime modules (``types``, ``descriptor``,
            ``synchronizer``) referenced in generated code. Use a vendored package for
            wheels that should not depend on the PyPI ``synchronicity`` distribution.
        emitter: Optional codegen backend (defaults to sync/async wrapper emitter)

    Returns:
        Dict mapping module names to their generated code
    """
    synchronized_classes = collect_synchronized_types(modules)
    gen = emitter or SyncAsyncWrapperEmitter(runtime_package=runtime_package)

    result = {}
    for module in modules:
        code = compile_module(module, synchronized_classes, emitter=gen)
        if code:
            result[module.target_module] = code

    return result
