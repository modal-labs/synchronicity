"""Protocol for pluggable codegen backends (sync/async wrappers, async-only proxies, etc.)."""

from __future__ import annotations

from typing import Protocol

from ..ir import ModuleCompilationIR


class CodegenEmitter(Protocol):
    """Emit wrapper module source from a :class:`~synchronicity.codegen.ir.ModuleCompilationIR`."""

    def emit_module(
        self,
        ir: ModuleCompilationIR,
    ) -> str:
        """Return full source for ``ir.target_module`` using only the IR."""
        ...
