"""Tests for parse-only codegen IR (no emission)."""

from __future__ import annotations

from synchronicity import Module
from synchronicity.codegen.ir import ModuleCompilationIR
from synchronicity.codegen.parse import build_module_compilation_ir, parse_module_level_function_ir
from synchronicity.codegen.transformer_ir import AwaitableTypeIR, IdentityTypeIR, ImplQualifiedRef


def test_parse_module_level_function_ir_async_is_awaitable_ir():
    async def impl() -> int:
        return 1

    ir = parse_module_level_function_ir(impl, "out_mod", {}, globals_dict=globals())
    assert ir.needs_async_wrapper is True
    assert ir.is_async_gen is False
    assert isinstance(ir.return_transformer_ir, AwaitableTypeIR)
    assert isinstance(ir.return_transformer_ir.inner, IdentityTypeIR)
    assert ir.return_transformer_ir.inner.signature_text == "int"
    assert ir.impl_ref == ImplQualifiedRef(impl.__module__, impl.__qualname__)


def test_build_module_compilation_ir_uses_qualified_refs():
    m = Module("generated.example")

    @m.wrap_class
    class Service:
        async def run(self) -> None:
            pass

    @m.wrap_function
    async def top_level() -> None:
        pass

    sync_types: dict = {Service: ("generated.example", "Service")}
    ir = build_module_compilation_ir(m, sync_types)

    assert isinstance(ir, ModuleCompilationIR)
    assert ir.target_module == "generated.example"
    assert ir.class_refs == (ImplQualifiedRef(Service.__module__, Service.__qualname__),)
    assert ir.function_refs == (ImplQualifiedRef(top_level.__module__, top_level.__qualname__),)
    assert len(ir.class_wrappers) == 1
    assert ir.class_wrappers[0].wrapper_class_name == "Service"
    assert len(ir.module_functions_ir) == 1
    assert ir.module_functions_ir[0].impl_ref == ir.function_refs[0]
    assert ir.has_wrapped_classes is True
