"""Tests for parse-only codegen IR (no emission)."""

from __future__ import annotations

import ast
import datetime
import pytest
import subprocess
import sys
import time
import typing
from inspect import Signature
from typing import Generic, TypeVar

from synchronicity2 import Module
from synchronicity2.codegen.default_expressions import resolve_parameter_default_expressions
from synchronicity2.codegen.ir import (
    ClassPropertyWrapperIR,
    ManualClassAttributeAccessKind,
    ManualReexportIR,
    ModuleCompilationIR,
    ModuleImportRefIR,
    PropertyWrapperIR,
)
from synchronicity2.codegen.parse import (
    build_module_compilation_ir,
    parse_class_wrapper_ir,
    parse_method_wrapper_ir,
    parse_module_level_function_ir,
)
from synchronicity2.codegen.transformer_ir import (
    AsyncContextManagerTypeIR,
    AwaitableTypeIR,
    CallableTypeIR,
    IdentityTypeIR,
    ImplQualifiedRef,
    SequenceTypeIR,
    SubscriptedWrappedClassTypeIR,
    UnionTypeIR,
    WrappedClassTypeIR,
    WrapperRef,
)
from synchronicity2.descriptor import classproperty, function_with_aio, method_with_aio

PARSE_DEFAULT_GREETING = "hello"

_SEQUENCE_CALLABLE_PARSE_MODULE = Module("generated.sequence_callable_parse")


@_SEQUENCE_CALLABLE_PARSE_MODULE.wrap_class()
class _SequenceCallableParseNode:
    pass


@_SEQUENCE_CALLABLE_PARSE_MODULE.wrap_function()
async def _sequence_callable_parse_clone_all(
    nodes: typing.Sequence[_SequenceCallableParseNode],
) -> typing.Sequence[_SequenceCallableParseNode]:
    return list(nodes)


@_SEQUENCE_CALLABLE_PARSE_MODULE.wrap_function()
def _sequence_callable_parse_make_callback(
    node: _SequenceCallableParseNode,
) -> typing.Callable[..., typing.Sequence[_SequenceCallableParseNode]]:
    return lambda *args, **kwargs: [node]


def parse_builtin_default(value: object = "hello") -> None:
    return None


def parse_multiline_default(
    value: tuple[int, int] = (
        1,
        2,
    ),
) -> None:
    return None


def parse_positional_keyword_defaults(a, /, b: int = 10, *, c: str = "hello", d: bool = False) -> None:
    return None


def parse_impl_module_default(value: str = PARSE_DEFAULT_GREETING) -> None:
    return None


def parse_qualified_import_default(pipe: int = subprocess.PIPE) -> None:
    return None


def parse_datetime_annotation(value: datetime.datetime) -> datetime.datetime:
    return value


def parse_unstable_default(value: float = time.time()) -> None:
    return None


class ParseDefaultService:
    async def configure(self, greeting: str = "hello", *, retries: int = 3) -> None:
        return None


_RENAMED_EXPORTS_MODULE = Module("generated.renamed")
RenameT = TypeVar("RenameT")


@_RENAMED_EXPORTS_MODULE.wrap_class(name="PublicService")
class _RenamedImplService(Generic[RenameT]):
    async def get(self) -> RenameT:
        raise NotImplementedError


@_RENAMED_EXPORTS_MODULE.wrap_function(name="make_service")
async def _renamed_make_service() -> _RenamedImplService[int]:
    raise NotImplementedError


@_RENAMED_EXPORTS_MODULE.wrap_class()
class _DefaultNamedService:
    async def get(self) -> int:
        raise NotImplementedError


@_RENAMED_EXPORTS_MODULE.wrap_function()
async def _default_named_factory() -> _DefaultNamedService:
    raise NotImplementedError


@_RENAMED_EXPORTS_MODULE.wrap_class(name="_ExplicitlyPrivateService")
class _ExplicitlyPrivateServiceImpl:
    async def get(self) -> int:
        raise NotImplementedError


@_RENAMED_EXPORTS_MODULE.wrap_function(name="_explicitly_private_factory")
async def _explicitly_private_factory_impl() -> _ExplicitlyPrivateServiceImpl:
    raise NotImplementedError


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


def test_resolve_parameter_default_expressions_preserves_exact_source_slices():
    resolved = resolve_parameter_default_expressions(
        parse_multiline_default,
        Signature.from_callable(parse_multiline_default),
        impl_module=sys.modules[__name__],
        source_label_prefix=f"{__name__}.parse_multiline_default",
    )

    assert resolved["value"].expression == "(\n        1,\n        2,\n    )"
    assert resolved["value"].import_refs == ()


def test_parse_module_level_function_ir_preserves_positional_and_keyword_only_defaults():
    ir = parse_module_level_function_ir(parse_positional_keyword_defaults, "out_mod", globals_dict=globals())

    assert tuple(param.default_expr for param in ir.parameters) == (None, "10", '"hello"', "False")
    assert tuple(param.default_import_refs for param in ir.parameters) == ((), (), (), ())


def test_parse_method_wrapper_ir_preserves_default_values():
    ir = parse_method_wrapper_ir(
        ParseDefaultService.configure,
        "configure",
        ParseDefaultService,
        globals_dict=globals(),
    )

    assert tuple(param.default_expr for param in ir.parameters) == ('"hello"', "3")
    assert tuple(param.default_import_refs for param in ir.parameters) == ((), ())


def test_parse_module_level_function_ir_preserves_builtin_source_default():
    ir = parse_module_level_function_ir(parse_builtin_default, "out_mod", globals_dict=globals())

    assert ir.parameters[0].default_expr == '"hello"'
    assert ir.parameters[0].default_import_refs == ()


def test_parse_module_level_function_ir_prefixes_impl_module_for_module_constants():
    ir = parse_module_level_function_ir(parse_impl_module_default, "out_mod", globals_dict=globals())

    assert ir.parameters[0].default_expr == f"{__name__}.PARSE_DEFAULT_GREETING"
    assert ir.parameters[0].default_import_refs == ()


def test_parse_module_level_function_ir_keeps_qualified_module_defaults_with_import_refs():
    ir = parse_module_level_function_ir(parse_qualified_import_default, "out_mod", globals_dict=globals())

    assert ir.parameters[0].default_expr == "subprocess.PIPE"
    assert ir.parameters[0].default_import_refs == (ModuleImportRefIR(module="subprocess", name="subprocess"),)


def test_parse_module_level_function_ir_keeps_annotation_import_modules():
    ir = parse_module_level_function_ir(parse_datetime_annotation, "out_mod", globals_dict=globals())

    assert ir.parameters[0].annotation_ir == IdentityTypeIR(
        signature_text="datetime.datetime",
        import_modules=("datetime",),
    )
    assert ir.return_transformer_ir == IdentityTypeIR(
        signature_text="datetime.datetime",
        import_modules=("datetime",),
    )


def test_parse_module_level_function_ir_rejects_missing_source(monkeypatch):
    monkeypatch.setattr(
        "synchronicity2.codegen.default_expressions.inspect.getsource",
        lambda _func: (_ for _ in ()).throw(OSError("no source")),
    )

    with pytest.raises(TypeError, match=r"Could not recover source"):
        parse_module_level_function_ir(parse_builtin_default, "out_mod", globals_dict=globals())


def test_parse_module_level_function_ir_rejects_unextractable_source_segment(monkeypatch):
    original_get_source_segment = ast.get_source_segment

    def patched_get_source_segment(source, node, *, padded=False):
        if isinstance(node, ast.Constant) and node.value == "hello":
            return None
        return original_get_source_segment(source, node, padded=padded)

    monkeypatch.setattr("synchronicity2.codegen.default_expressions.ast.get_source_segment", patched_get_source_segment)

    with pytest.raises(TypeError, match=r"parameter 'value'.*could not be extracted from source"):
        parse_module_level_function_ir(parse_builtin_default, "out_mod", globals_dict=globals())


def test_parse_module_level_function_ir_rejects_unstable_default_value():
    with pytest.raises(TypeError, match=r"parameter 'value'.*unsupported default expression"):
        parse_module_level_function_ir(parse_unstable_default, "out_mod", globals_dict=globals())


def test_parse_module_level_function_ir_rejects_closure_local_defaults():
    local_default = "hello"

    def impl(value: str = local_default) -> None:
        return None

    with pytest.raises(TypeError, match=r"parameter 'value'.*unsupported default expression"):
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


def test_build_module_compilation_ir_preserves_registered_export_names():
    ir = build_module_compilation_ir(_RENAMED_EXPORTS_MODULE)

    class_wrappers = {wrapper.impl_ref.qualname.rpartition(".")[2]: wrapper for wrapper in ir.class_wrappers}
    function_irs = {function.impl_ref.qualname.rpartition(".")[2]: function for function in ir.module_functions_ir}

    assert class_wrappers["_RenamedImplService"].wrapper_ref == WrapperRef("generated.renamed", "PublicService")
    assert function_irs["_renamed_make_service"].export_name == "make_service"
    assert isinstance(function_irs["_renamed_make_service"].return_transformer_ir, AwaitableTypeIR)
    assert isinstance(function_irs["_renamed_make_service"].return_transformer_ir.inner, SubscriptedWrappedClassTypeIR)
    assert function_irs["_renamed_make_service"].return_transformer_ir.inner.wrapper == WrapperRef(
        "generated.renamed",
        "PublicService",
    )
    assert class_wrappers["_DefaultNamedService"].wrapper_ref == WrapperRef("generated.renamed", "DefaultNamedService")
    assert function_irs["_default_named_factory"].export_name == "default_named_factory"
    assert class_wrappers["_ExplicitlyPrivateServiceImpl"].wrapper_ref == WrapperRef(
        "generated.renamed",
        "_ExplicitlyPrivateService",
    )
    assert function_irs["_explicitly_private_factory_impl"].export_name == "_explicitly_private_factory"


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

    ns: dict = {"Module": Module, "__name__": __name__}
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


def test_parse_class_sync_classproperty():
    """Sync @classproperty is collected into ClassWrapperIR.class_properties."""

    ns: dict = {"Module": Module, "classproperty": classproperty}
    exec(
        """
m = Module("generated.classprop_parse")
@m.wrap_class()
class Manager:
    pass
@m.wrap_class()
class Service:
    _manager = Manager()
    @classproperty
    def manager(cls) -> Manager:
        return cls._manager
""",
        ns,
    )
    Service = ns["Service"]
    Manager = ns["Manager"]
    ir = parse_class_wrapper_ir(Service, "generated.classprop_parse", globals_dict=ns)
    assert len(ir.class_properties) == 1
    prop = ir.class_properties[0]
    assert isinstance(prop, ClassPropertyWrapperIR)
    assert prop.name == "manager"
    assert isinstance(prop.return_transformer_ir, WrappedClassTypeIR)
    assert prop.return_transformer_ir.impl == ImplQualifiedRef(Manager.__module__, Manager.__qualname__)
    assert prop.return_transformer_ir.wrapper == WrapperRef("generated.classprop_parse", "Manager")


def test_parse_class_async_classproperty_raises():
    """An async getter on a @classproperty must be rejected at parse time."""

    ns: dict = {"Module": Module, "classproperty": classproperty}
    exec(
        """
m = Module("generated.async_classprop")
@m.wrap_class()
class Bad:
    @classproperty
    async def broken(cls) -> int:
        return 1
""",
        ns,
    )
    Bad = ns["Bad"]
    with pytest.raises(TypeError, match="Class properties must be synchronous"):
        parse_class_wrapper_ir(Bad, "generated.async_classprop", globals_dict=ns)


def test_parse_class_vendored_classproperty_descriptor():
    """Vendored runtimes may provide an equivalent classproperty descriptor type."""

    ns: dict = {"Module": Module}
    exec(
        """
class classproperty:
    def __init__(self, fget):
        if not isinstance(fget, classmethod):
            fget = classmethod(fget)
        self.fget = fget

    def __get__(self, obj, owner):
        return self.fget.__get__(None, owner)()

m = Module("generated.vendored_classprop")
@m.wrap_class()
class Item:
    pass
@m.wrap_class()
class Service:
    @classproperty
    def current(cls) -> Item:
        return Item()
""",
        ns,
    )
    Service = ns["Service"]
    Item = ns["Item"]

    ir = parse_class_wrapper_ir(Service, "generated.vendored_classprop", globals_dict=ns)

    assert len(ir.class_properties) == 1
    assert isinstance(ir.class_properties[0].return_transformer_ir, WrappedClassTypeIR)
    assert ir.class_properties[0].return_transformer_ir.impl == ImplQualifiedRef(Item.__module__, Item.__qualname__)


def test_parse_class_forwarded_dunder_methods():
    """Selected data-model methods should be emitted as callable wrappers."""

    m = Module("generated.dunders")

    @m.wrap_class()
    class Box:
        async def __getitem__(self, key: str) -> int:
            return 1

        async def __setitem__(self, key: str, value: int) -> None:
            return None

        async def __contains__(self, key: str) -> bool:
            return True

        async def __delitem__(self, key: str) -> None:
            return None

    ir = parse_class_wrapper_ir(Box, "generated.dunders", globals_dict=locals())
    method_names = {method_ir.method_name for method_ir in ir.methods}

    assert {"__getitem__", "__setitem__", "__contains__", "__delitem__"} <= method_names


def test_parse_classmethod_async_context_manager_return_ir():
    """Classmethods returning async context managers should preserve wrapped yield translation."""

    from contextlib import asynccontextmanager

    m = Module("generated.class_cm")

    @m.wrap_class()
    class Item:
        pass

    @m.wrap_class()
    class Service:
        @classmethod
        @asynccontextmanager
        async def make(cls) -> typing.AsyncGenerator[Item, None]:
            yield Item()

    ir = parse_class_wrapper_ir(Service, "generated.class_cm", globals_dict=locals())
    make_ir = next(method_ir for method_ir in ir.methods if method_ir.method_name == "make")

    assert isinstance(make_ir.return_transformer_ir, AsyncContextManagerTypeIR)
    assert isinstance(make_ir.return_transformer_ir.value, WrappedClassTypeIR)


def test_parse_class_wrapper_ir_tolerates_class_dict_mutation_during_property_inspection():
    m = Module("generated.mutating_prop")

    class MutatingProperty(property):
        @property
        def fget(self):
            MutatingService._added_during_parse = lambda self: None
            return super().fget

    @m.wrap_class()
    class MutatingService:
        def _get_value(self) -> int:
            return 1

        value = MutatingProperty(_get_value)

    ir = parse_class_wrapper_ir(MutatingService, "generated.mutating_prop", globals_dict=locals())

    assert any(prop.name == "value" for prop in ir.properties)


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


def test_parse_sequence_and_callable_ellipsis_annotations():
    clone_ir = parse_module_level_function_ir(
        _sequence_callable_parse_clone_all,
        "generated.sequence_callable_parse",
        globals_dict=globals(),
    )
    callback_ir = parse_module_level_function_ir(
        _sequence_callable_parse_make_callback,
        "generated.sequence_callable_parse",
        globals_dict=globals(),
    )

    assert isinstance(clone_ir.parameters[0].annotation_ir, SequenceTypeIR)
    assert isinstance(clone_ir.parameters[0].annotation_ir.item, WrappedClassTypeIR)
    assert isinstance(clone_ir.return_transformer_ir, AwaitableTypeIR)
    assert isinstance(clone_ir.return_transformer_ir.inner, SequenceTypeIR)
    assert isinstance(clone_ir.return_transformer_ir.inner.item, WrappedClassTypeIR)

    assert isinstance(callback_ir.return_transformer_ir, CallableTypeIR)
    assert callback_ir.return_transformer_ir.params is None
    assert isinstance(callback_ir.return_transformer_ir.return_type, SequenceTypeIR)
    assert isinstance(callback_ir.return_transformer_ir.return_type.item, WrappedClassTypeIR)
