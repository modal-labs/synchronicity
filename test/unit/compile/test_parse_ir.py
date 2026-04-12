"""Tests for parse-only codegen IR (no emission)."""

from __future__ import annotations

from typing import Generic, TypeVar

from synchronicity import Module
from synchronicity.codegen.ir import ModuleCompilationIR
from synchronicity.codegen.parse import (
    build_module_compilation_ir,
    parse_class_wrapper_ir,
    parse_module_level_function_ir,
)
from synchronicity.codegen.transformer_ir import (
    AwaitableTypeIR,
    IdentityTypeIR,
    ImplQualifiedRef,
    WrappedClassTypeIR,
    WrapperRef,
)


def test_parse_module_level_function_ir_async_is_awaitable_ir():
    async def impl() -> int:
        return 1

    ir = parse_module_level_function_ir(impl, "out_mod", globals_dict=globals())
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

    ir = build_module_compilation_ir(m)

    assert isinstance(ir, ModuleCompilationIR)
    assert ir.target_module == "generated.example"
    assert ir.class_refs == (ImplQualifiedRef(Service.__module__, Service.__qualname__),)
    assert ir.function_refs == (ImplQualifiedRef(top_level.__module__, top_level.__qualname__),)
    assert len(ir.class_wrappers) == 1
    assert ir.class_wrappers[0].impl_ref.qualname.rpartition(".")[2] == "Service"
    assert len(ir.module_functions_ir) == 1
    assert ir.module_functions_ir[0].impl_ref == ir.function_refs[0]
    assert ir.has_wrapped_classes is True


def test_parse_class_wrapper_ir_inheritance_stores_impl_refs_not_wrapper_names():
    m = Module("generated.inherit_parse")

    @m.wrap_class
    class Base:
        async def base_m(self) -> None:
            pass

    @m.wrap_class
    class Sub(Base):
        async def sub_m(self) -> None:
            pass

    ir = parse_class_wrapper_ir(Sub, "generated.inherit_parse", globals_dict=globals())
    assert ir.wrapped_bases == (
        (ImplQualifiedRef(Base.__module__, Base.__qualname__), WrapperRef("generated.inherit_parse", "Base")),
    )
    assert ir.generic_type_parameters is None


def test_parse_class_wrapper_ir_generic_stores_type_parameter_names():
    m = Module("generated.generic_parse")
    T = TypeVar("T")

    @m.wrap_class
    class G(Generic[T]):
        async def get(self) -> T:
            raise NotImplementedError

    ir = parse_class_wrapper_ir(G, "generated.generic_parse", globals_dict=globals())
    assert ir.wrapped_bases == ()
    assert ir.generic_type_parameters == ("T",)


def test_parse_class_attributes_are_type_ir_not_wrapper_strings():
    """Class field annotations are TypeTransformerIR (e.g. WrappedClassTypeIR), not emitted names.

    Defined via ``exec`` without PEP 563 so ``inner: Inner`` resolves to a live type (not a string).
    """

    ns: dict = {"Module": Module}
    exec(
        """
m = Module("generated.attr_parse")
@m.wrap_class
class Inner:
    pass
@m.wrap_class
class Holder:
    inner: Inner
""",
        ns,
    )
    Inner = ns["Inner"]
    Holder = ns["Holder"]
    ir = parse_class_wrapper_ir(Holder, "generated.attr_parse", globals_dict=ns)
    assert len(ir.attributes) == 1
    _name, ann_ir = ir.attributes[0]
    assert isinstance(ann_ir, WrappedClassTypeIR)
    assert ann_ir.impl == ImplQualifiedRef(Inner.__module__, Inner.__qualname__)
    assert ann_ir.wrapper == WrapperRef("generated.attr_parse", "Inner")
