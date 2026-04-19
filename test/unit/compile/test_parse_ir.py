"""Tests for parse-only codegen IR (no emission)."""

from __future__ import annotations

import pytest
import typing
from typing import Generic, TypeVar

from synchronicity import Module
from synchronicity.codegen.ir import (
    ManualClassAttributeAccessKind,
    ManualReexportIR,
    ModuleCompilationIR,
    PropertyWrapperIR,
)
from synchronicity.codegen.parse import (
    build_module_compilation_ir,
    parse_class_wrapper_ir,
    parse_method_wrapper_ir,
    parse_module_level_function_ir,
)
from synchronicity.codegen.transformer_ir import (
    AwaitableTypeIR,
    IdentityTypeIR,
    ImplQualifiedRef,
    UnionTypeIR,
    WrappedClassTypeIR,
    WrapperRef,
)
from synchronicity.descriptor import function_with_aio, method_with_aio


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


@pytest.mark.parametrize(
    "default_value",
    [
        None,
        True,
        42,
        1.5,
        "hello",
        b"bytes",
        (1, "two"),
        [1, 2],
        {"a": 1},
        {1, 2},
        frozenset({1, 2}),
        range(0, 3),
        slice(1, 2, 3),
        Ellipsis,
    ],
)
def test_parse_module_level_function_ir_preserves_supported_default_values(default_value):
    def impl(value: object = default_value) -> None:
        return None

    ir = parse_module_level_function_ir(impl, "out_mod", globals_dict=locals())

    assert ir.parameters[0].default_repr == repr(default_value)


def test_parse_module_level_function_ir_preserves_positional_and_keyword_only_defaults():
    def impl(a, /, b: int = 10, *, c: str = "hello", d: bool = False) -> None:
        return None

    ir = parse_module_level_function_ir(impl, "out_mod", globals_dict=locals())

    assert tuple(param.default_repr for param in ir.parameters) == (None, "10", "'hello'", "False")


def test_parse_method_wrapper_ir_preserves_default_values():
    class Service:
        async def configure(self, greeting: str = "hello", *, retries: int = 3) -> None:
            return None

    ir = parse_method_wrapper_ir(Service.configure, "configure", Service, globals_dict=locals())

    assert tuple(param.default_repr for param in ir.parameters) == ("'hello'", "3")


def test_parse_module_level_function_ir_rejects_non_python_default_repr():
    bad_default = object()

    def impl(value: object = bad_default) -> None:
        return None

    with pytest.raises(TypeError, match=r"parameter 'value'.*not valid Python source"):
        parse_module_level_function_ir(impl, "out_mod", globals_dict=locals())


def test_parse_module_level_function_ir_rejects_default_repr_needing_non_builtin_globals():
    class NeedsImport:
        def __repr__(self) -> str:
            return "pathlib.Path('demo')"

    bad_default = NeedsImport()

    def impl(value: object = bad_default) -> None:
        return None

    with pytest.raises(TypeError, match=r"parameter 'value'.*not executable in generated wrapper module scope"):
        parse_module_level_function_ir(impl, "out_mod", globals_dict=locals())


def test_parse_module_level_function_ir_rejects_non_round_tripping_default_repr():
    class WrongRepr:
        def __repr__(self) -> str:
            return "1"

    bad_default = WrongRepr()

    def impl(value: object = bad_default) -> None:
        return None

    with pytest.raises(TypeError, match=r"parameter 'value'.*round-trips to int, not WrongRepr"):
        parse_module_level_function_ir(impl, "out_mod", globals_dict=locals())


def test_build_module_compilation_ir_uses_qualified_refs():
    m = Module("generated.example")

    @m.wrap_class()
    class Service:
        async def run(self) -> None:
            pass

    @m.wrap_function()
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


def test_wrap_decorators_require_factory_call() -> None:
    m = Module("generated.decorator_factory_only")

    with pytest.raises(TypeError):
        m.wrap_function(lambda: None)

    with pytest.raises(TypeError):
        m.wrap_class(type("Service", (), {}))


def test_module_public_members_are_minimal() -> None:
    public_names = {
        name
        for name in Module.__dict__
        if not name.startswith("_") and not (name.startswith("__") and name.endswith("__"))
    }
    assert public_names == {"target_module", "synchronizer_name", "manual_wrapper", "wrap_function", "wrap_class"}


def test_parse_class_wrapper_ir_inheritance_stores_impl_refs_not_wrapper_names():
    m = Module("generated.inherit_parse")

    @m.wrap_class()
    class Base:
        async def base_m(self) -> None:
            pass

    @m.wrap_class()
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

    @m.wrap_class()
    class G(Generic[T]):
        async def get(self) -> T:
            raise NotImplementedError

    ir = parse_class_wrapper_ir(G, "generated.generic_parse", globals_dict=globals())
    assert ir.wrapped_bases == ()
    assert ir.generic_type_parameters == ("T",)


def test_parse_class_sync_property_readonly():
    """Sync read-only @property is collected into ClassWrapperIR.properties."""

    ns: dict = {"Module": Module}
    exec(
        """
m = Module("generated.prop_parse")
@m.wrap_class()
class Cfg:
    @property
    def name(self) -> str:
        return "hello"
""",
        ns,
    )
    Cfg = ns["Cfg"]
    ir = parse_class_wrapper_ir(Cfg, "generated.prop_parse", globals_dict=ns)
    assert len(ir.properties) == 1
    prop = ir.properties[0]
    assert isinstance(prop, PropertyWrapperIR)
    assert prop.name == "name"
    assert isinstance(prop.return_transformer_ir, IdentityTypeIR)
    assert prop.return_transformer_ir.signature_text == "str"
    assert prop.has_setter is False
    assert prop.setter_value_ir is None


def test_parse_class_sync_property_readwrite():
    """Sync read-write @property captures both getter and setter IR."""

    ns: dict = {"Module": Module}
    exec(
        """
m = Module("generated.prop_rw")
@m.wrap_class()
class Cfg:
    @property
    def count(self) -> int:
        return 0
    @count.setter
    def count(self, value: int) -> None:
        pass
""",
        ns,
    )
    Cfg = ns["Cfg"]
    ir = parse_class_wrapper_ir(Cfg, "generated.prop_rw", globals_dict=ns)
    assert len(ir.properties) == 1
    prop = ir.properties[0]
    assert prop.name == "count"
    assert prop.has_setter is True
    assert isinstance(prop.return_transformer_ir, IdentityTypeIR)
    assert isinstance(prop.setter_value_ir, IdentityTypeIR)
    assert prop.setter_value_ir.signature_text == "int"


def test_parse_class_async_property_raises():
    """An async getter on a @property must be rejected at parse time."""

    ns: dict = {"Module": Module}
    exec(
        """
m = Module("generated.async_prop")
@m.wrap_class()
class Bad:
    @property
    async def broken(self) -> int:
        return 1
""",
        ns,
    )
    Bad = ns["Bad"]
    with pytest.raises(TypeError, match="async"):
        parse_class_wrapper_ir(Bad, "generated.async_prop", globals_dict=ns)


def test_parse_class_attributes_are_type_ir_not_wrapper_strings():
    """Class field annotations are TypeTransformerIR (e.g. WrappedClassTypeIR), not emitted names.

    Defined via ``exec`` without PEP 563 so ``inner: Inner`` resolves to a live type (not a string).
    """

    ns: dict = {"Module": Module}
    exec(
        """
m = Module("generated.attr_parse")
@m.wrap_class()
class Inner:
    pass
@m.wrap_class()
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


def test_parse_module_function_overloads_are_captured_in_ir():
    m = Module("generated.overload_parse")

    @m.wrap_class()
    class Item:
        pass

    @typing.overload
    async def convert(value: int) -> int: ...

    @typing.overload
    async def convert(value: Item) -> Item: ...

    @m.wrap_function()
    async def convert(value) -> object:
        return value

    ir = parse_module_level_function_ir(convert, "generated.overload_parse", globals_dict=locals())

    assert len(ir.overloads) == 2
    int_overload, wrapped_overload = ir.overloads
    assert isinstance(int_overload.parameters[0].annotation_ir, IdentityTypeIR)
    assert isinstance(wrapped_overload.parameters[0].annotation_ir, WrappedClassTypeIR)
    assert isinstance(wrapped_overload.return_transformer_ir, AwaitableTypeIR)
    assert isinstance(wrapped_overload.return_transformer_ir.inner, WrappedClassTypeIR)
    assert wrapped_overload.return_transformer_ir.inner.wrapper == WrapperRef("generated.overload_parse", "Item")


def test_parse_method_overloads_are_captured_in_ir():
    m = Module("generated.method_overload_parse")

    @m.wrap_class()
    class Item:
        pass

    @m.wrap_class()
    class Service:
        @typing.overload
        async def convert(self, value: int) -> int: ...

        @typing.overload
        async def convert(self, value: Item) -> Item: ...

        async def convert(self, value) -> object:
            return value

    ir = parse_class_wrapper_ir(Service, "generated.method_overload_parse", globals_dict=locals())
    method_ir = next(method for method in ir.methods if method.method_name == "convert")

    assert len(method_ir.overloads) == 2
    int_overload, wrapped_overload = method_ir.overloads
    assert isinstance(int_overload.parameters[0].annotation_ir, IdentityTypeIR)
    assert isinstance(wrapped_overload.parameters[0].annotation_ir, WrappedClassTypeIR)
    assert isinstance(wrapped_overload.return_transformer_ir, AwaitableTypeIR)
    assert isinstance(wrapped_overload.return_transformer_ir.inner, WrappedClassTypeIR)
    assert wrapped_overload.return_transformer_ir.inner.wrapper == WrapperRef("generated.method_overload_parse", "Item")


def test_parse_non_optional_unions_are_captured_in_ir():
    m = Module("generated.union_parse")

    @m.wrap_class()
    class Item:
        pass

    @m.wrap_function()
    async def convert(value: int | Item) -> int | Item:
        return value

    ir = parse_module_level_function_ir(convert, "generated.union_parse", globals_dict=locals())

    assert isinstance(ir.parameters[0].annotation_ir, UnionTypeIR)
    assert isinstance(ir.parameters[0].annotation_ir.items[0], IdentityTypeIR)
    assert isinstance(ir.parameters[0].annotation_ir.items[1], WrappedClassTypeIR)
    assert isinstance(ir.return_transformer_ir, AwaitableTypeIR)
    assert isinstance(ir.return_transformer_ir.inner, UnionTypeIR)
    assert isinstance(ir.return_transformer_ir.inner.items[0], IdentityTypeIR)
    assert isinstance(ir.return_transformer_ir.inner.items[1], WrappedClassTypeIR)


def test_build_module_compilation_ir_collects_manual_reexports_separately():
    m = Module("generated.manual_exports")

    class _FunctionWithAio:
        def __init__(self, sync_impl: typing.Callable[..., typing.Any]):
            self._sync_impl = sync_impl

        def __call__(self) -> str:
            return self._sync_impl()

    @m.wrap_function()
    @m.manual_wrapper()
    @function_with_aio(_FunctionWithAio)
    def forwarded() -> str:
        return "ok"

    @m.wrap_class()
    @m.manual_wrapper()
    class ForwardedType:
        pass

    ir = build_module_compilation_ir(m)

    assert ir.module_functions_ir == ()
    assert ir.class_wrappers == ()
    assert set(ir.manual_reexports) == {
        ManualReexportIR(
            impl_ref=ImplQualifiedRef(forwarded._sync_impl.__module__, forwarded._sync_impl.__qualname__),
            export_name="forwarded",
        ),
        ManualReexportIR(
            impl_ref=ImplQualifiedRef(ForwardedType.__module__, ForwardedType.__qualname__),
            export_name="ForwardedType",
        ),
    }


def test_parse_class_wrapper_ir_collects_manual_with_aio_methods():
    m = Module("generated.manual_method_parse")

    class _MethodWithAio:
        def __init__(
            self,
            sync_impl: typing.Callable[..., typing.Any],
            wrapper_instance: typing.Any,
            wrapper_class: type,
            _from_impl: typing.Callable[[typing.Any], typing.Any],
        ):
            self._sync_impl = sync_impl

        def __call__(self, value: int) -> int:
            return self._sync_impl(value)

        async def aio(self, value: int) -> int:
            return value

    @m.wrap_class()
    class Service:
        @m.manual_wrapper()
        @method_with_aio(_MethodWithAio)
        def manual(self, value: int) -> int:
            return value

        async def generated(self, value: int) -> int:
            return value

    ir = parse_class_wrapper_ir(
        Service,
        "generated.manual_method_parse",
        globals_dict=locals(),
        manual_wrapper_ids=m._manual_wrapper_ids,
    )

    assert tuple(method.method_name for method in ir.methods) == ("generated",)
    assert ir.manual_attributes == (
        ir.manual_attributes[0].__class__(
            name="manual",
            access_kind=ManualClassAttributeAccessKind.ATTRIBUTE,
        ),
    )
