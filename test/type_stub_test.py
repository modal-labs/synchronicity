import collections
import functools
import importlib
import pathlib
import pytest
import sys
import typing
from textwrap import dedent

import typing_extensions

import synchronicity
from synchronicity import classproperty, overload_tracking
from synchronicity.async_wrap import asynccontextmanager
from synchronicity.type_stubs import StubEmitter

from .type_stub_helpers import some_mod


def noop(): ...


def arg_no_anno(arg1): ...


def scalar_args(arg1: str, arg2: int) -> float:
    return 0


def generic_other_module_arg(arg: typing.List[some_mod.Foo]): ...


async def async_func() -> str:
    return "hello"


def single_line_docstring_func():
    """I have a single line docstring"""


def multi_line_docstring_func():
    """I have a docstring

    with multiple lines
    """


def nested_docstring_func():
    """I have a docstring

    ```
    def example():
        \"""SUPRISE! SO DO I!\"""
    ```
    """


def deranged_docstring_func():
    """I have \""" and also ''' for some reason"""


class SingleLineDocstringClass:
    """I have a single line docstring"""


class MultiLineDocstringClass:
    """I have a docstring

    with multiple lines
    """


class ClassWithMethodsWithDocstrings:
    def method_with_single_line_docstring(self):
        """I have a docstring"""

    def method_with_multi_line_docstring(self):
        """I have a docstring

        with multiple lines
        """


def _function_source(func, target_module=__name__):
    stub_emitter = StubEmitter(target_module)
    stub_emitter.add_function(func, func.__name__)
    return stub_emitter.get_source()


def _class_source(cls, target_module=__name__):
    stub_emitter = StubEmitter(target_module)
    stub_emitter.add_class(cls, cls.__name__)
    return stub_emitter.get_source()


def test_function_basics():
    assert _function_source(noop) == "def noop():\n    ...\n"
    assert _function_source(arg_no_anno) == "def arg_no_anno(arg1):\n    ...\n"
    assert _function_source(scalar_args) == "def scalar_args(arg1: str, arg2: int) -> float:\n    ...\n"


def test_function_with_imports():
    assert (
        _function_source(generic_other_module_arg, target_module="dummy")
        == """import test.type_stub_helpers.some_mod
import typing

def generic_other_module_arg(arg: typing.List[test.type_stub_helpers.some_mod.Foo]):
    ...
"""
    )


def test_async_func():
    assert _function_source(async_func) == "async def async_func() -> str:\n    ...\n"


def test_async_gen():
    async def async_gen() -> typing.AsyncGenerator[int, None]:
        yield 0

    assert (
        _function_source(async_gen)
        == "import typing\n\ndef async_gen() -> typing.AsyncGenerator[int, None]:\n    ...\n"
    )

    def weird_async_gen() -> typing.AsyncGenerator[int, None]:
        # non-async function that returns an async generator
        async def gen():
            yield 0

        return gen()

    assert (
        _function_source(weird_async_gen)
        == "import typing\n\ndef weird_async_gen() -> typing.AsyncGenerator[int, None]:\n    ...\n"
    )

    async def it() -> typing.AsyncIterator[str]:  # this is the/a correct annotation
        yield "hello"

    src = _function_source(it)
    assert "yield" not in src
    # since the yield keyword is removed in a type stub, the async prefix needs to be removed as well
    # to avoid "double asyncness" (while keeping the remaining annotation)
    assert "async" not in src
    assert "def it() -> typing.AsyncIterator[str]:" in src


class MixedClass:
    class_var: str

    def some_method(self) -> bool:
        return False

    @classmethod
    def some_class_method(cls) -> int:
        return 1

    @staticmethod
    def some_staticmethod() -> float:
        return 0.0

    @property
    def some_property(self) -> str:
        return ""

    @some_property.setter
    def some_property(self, val):
        print(val)

    @some_property.deleter
    def some_property(self, val):
        print(val)

    @classproperty
    def class_property(cls):
        return 1


def test_class_generation():
    emitter = StubEmitter(__name__)
    emitter.add_class(MixedClass, "MixedClass")
    source = emitter.get_source()
    last_assertion_location = None

    def assert_in_after_last(search_string):
        nonlocal last_assertion_location
        assert search_string in source
        if last_assertion_location is not None:
            new_location = source.find(search_string)
            assert new_location > last_assertion_location
            last_assertion_location = new_location

    indent = "    "
    assert_in_after_last("import synchronicity")
    assert_in_after_last("class MixedClass:")
    assert_in_after_last(f"{indent}class_var: str")
    assert_in_after_last(f"{indent}class_var: str")
    assert_in_after_last(f"{indent}def some_method(self) -> bool:\n{indent * 2}...")
    assert_in_after_last(f"{indent}@classmethod\n{indent}def some_class_method(cls) -> int:\n{indent * 2}...")
    assert_in_after_last(f"{indent}@staticmethod\n{indent}def some_staticmethod() -> float:")
    assert_in_after_last(f"{indent}@property\n{indent}def some_property(self) -> str:")
    assert_in_after_last(f"{indent}@some_property.setter\n{indent}def some_property(self, val):")
    assert_in_after_last(f"{indent}@some_property.deleter\n{indent}def some_property(self, val):")
    assert_in_after_last(f"{indent}@synchronicity.classproperty\n{indent}def class_property(cls):\n{indent * 2}...")


def merged_signature(*sigs):
    sig = sigs[0].copy()
    return sig


@pytest.mark.skipif(
    sys.version_info[:2] == (3, 14), reason="Updating annotations through __annotations__ does not work in Python 3.14"
)
def test_wrapped_function_with_new_annotations():
    """A wrapped function (in general, using functools.wraps/partial) would
    have an inspect.signature from the wrapped function by default
    and from the wrapper function is inspect.signature gets the follow_wrapped=True
    option. However, for the best type stub usability, the best would be to combine
    all layers of wrapping, adding any additional arguments or annotations as updates
    to the underlying wrapped function signature.

    This test makes sure we do just that.
    """

    def orig(arg: str): ...

    @functools.wraps(orig)
    def wrapper(extra_arg: int, *args, **kwargs):
        orig(*args, **kwargs)

    wrapper.__annotations__.update({"extra_arg": int, "arg": float})
    assert _function_source(wrapper) == "def orig(extra_arg: int, arg: float):\n    ...\n"


def test_wrapped_async_func_remains_async():
    async def orig(arg: str): ...

    @functools.wraps(orig)
    def wrapper(*args, **kwargs):
        return orig(*args, **kwargs)

    assert _function_source(wrapper) == "async def orig(arg: str):\n    ...\n"


class Base:
    def base_method(self) -> str:
        return ""


Base.__module__ = "basemod"
Base.__qualname__ = "Base"


class Based(Base):
    def sub(self) -> float:
        return 0


def test_base_class_included_and_imported():
    src = _class_source(Based)
    assert "import basemod" in src
    assert "class Based(basemod.Base):" in src
    assert "base_method" not in src  # base class method should not be in emitted stub


def test_typevar():
    T = typing.TypeVar("T")
    T.__module__ = "source_mod"

    def foo(arg: T) -> T:
        return arg

    src = _function_source(foo)
    assert "import source_mod" in src
    assert "def foo(arg: source_mod.T) -> source_mod.T" in src


def test_string_annotation():
    stub_emitter = StubEmitter("dummy")
    stub_emitter.add_variable(annotation="Foo", name="some_foo")  # string annotation
    src = stub_emitter.get_source()
    assert 'some_foo: "Foo"' in src or "some_foo: 'Foo'" in src


class Forwarder:
    def foo(self) -> typing.List["Forwardee"]: ...


class Forwardee: ...


def test_forward_ref():
    # add in the same order here:
    stub = StubEmitter(__name__)
    stub.add_class(Forwarder, "Forwarder")
    stub.add_class(Forwardee, "Forwardee")
    src = stub.get_source()
    assert "class Forwarder:" in src
    assert (
        "def foo(self) -> typing.List[Forwardee]:" in src
    )  # should technically be quoted 'Forwardee', but non-strings seem ok in pure type stubs


def test_optional():
    # Not super important, but try to preserve typing.Optional as typing.Optional instead of typing.Union[None, ...]
    # This only works on Python 3.10+, since 3.9 and earlier do "eager" conversion when creating the type
    def f() -> typing.Optional[str]: ...

    wrapped_f = synchronizer.create_blocking(f, "wrapped_f", __name__)

    src = _function_source(wrapped_f)
    # TODO: 3.14 does not preserve the typing.Optional[str]
    if sys.version_info[:2] == (3, 14):
        assert "typing.Union[str, None]" in src
    elif sys.version_info[:2] >= (3, 10):
        assert "typing.Optional[str]" in src
    else:
        assert "typing.Union[str, None]" in src


class SelfRefFoo:
    def foo(self) -> "SelfRefFoo":
        return self


def test_self_ref():
    src = _class_source(SelfRefFoo)
    assert (
        "def foo(self) -> SelfRefFoo" in src
    )  # should technically be 'Foo' but non-strings seem ok in pure type stubs


class _Foo:
    @staticmethod
    async def clone(foo: "_Foo") -> "_Foo":
        return foo


synchronizer = synchronicity.Synchronizer()


@pytest.fixture(autouse=True, scope="module")
def synchronizer_teardown():
    yield
    synchronizer._close_loop()  # prevent "unclosed event loop" warnings


Foo = synchronizer.create_blocking(_Foo, "Foo", __name__)


def test_synchronicity_type_translation():
    async def _get_foo(foo: _Foo) -> typing.AsyncContextManager[_Foo]:
        return foo

    get_foo = synchronizer.create_blocking(_get_foo, "get_foo", __name__)
    src = _function_source(get_foo)

    print(src)
    assert "class __get_foo_spec(typing_extensions.Protocol):" in src
    assert (
        "    def __call__(self, /, foo: Foo) -> synchronicity.combined_types.AsyncAndBlockingContextManager[Foo]" in src
    )
    # python 3.13 has an exit type generic argument, e.g. typing.AsyncContextManager[Foo, bool | None]
    # but we want the type stubs to work on older versions of python too (without conditionals everywhere):
    assert "    async def aio(self, /, foo: Foo) -> typing.AsyncContextManager[Foo]" in src
    assert "get_foo: __get_foo_spec"


def test_synchronicity_wrapped_class():
    src = _class_source(Foo)
    print(src)
    # assert "__init__" not in Foo
    assert "class __clone_spec(typing_extensions.Protocol):" in src
    assert "    def __call__(self, /, foo: Foo) -> Foo" in src
    assert "    async def aio(self, /, foo: Foo) -> Foo" in src
    assert "clone: typing.ClassVar[__clone_spec]" in src


class _WithClassMethod:
    @classmethod
    def classy(cls): ...

    async def meth(self, arg: bool) -> int:
        return 0


WithClassMethod = synchronizer.create_blocking(_WithClassMethod, "WithClassMethod", __name__)


def test_synchronicity_class():
    src = _class_source(WithClassMethod)
    assert "    @classmethod" in src
    assert "    def classy(cls):" in src

    assert "__meth_spec" in src

    assert (
        """
    class __meth_spec(typing_extensions.Protocol):
        def __call__(self, /, arg: bool) -> int:
            ...

        async def aio(self, /, arg: bool) -> int:
            ...

    meth: __meth_spec
"""
        in src
    )


T = typing.TypeVar("T")
P = typing_extensions.ParamSpec("P")


Translated_T = synchronizer.create_blocking(T, "Translated_T", __name__)
Translated_P = synchronizer.create_blocking(P, "Translated_P", __name__)


class MyGeneric(typing.Generic[T]): ...


BlockingMyGeneric = synchronizer.create_blocking(
    MyGeneric,
    "BlockingMyGeneric",
    __name__,
)


def test_custom_generic():
    # TODO: build out this test a bit, as it currently creates an invalid stub (missing base types)
    src = _class_source(BlockingMyGeneric)

    class Specific(MyGeneric[str]): ...

    src = _class_source(Specific)
    assert "class Specific(MyGeneric[str]):" in src


class ParamSpecGeneric(typing.Generic[P, T]):
    async def meth(self, *args: P.args, **kwargs: P.kwargs) -> typing_extensions.Self: ...

    def syncfunc(self) -> T: ...


BlockingParamSpecGeneric = synchronizer.create_blocking(ParamSpecGeneric, "BlockingParamSpecGeneric", __name__)


def test_paramspec_generic():
    src = _class_source(BlockingParamSpecGeneric)
    assert "class BlockingParamSpecGeneric(typing.Generic[Translated_P, Translated_T])" in src

    assert "class __meth_spec(typing_extensions.Protocol[Translated_P_INNER, SUPERSELF]):" in src
    assert (
        "def __call__(self, /, *args: Translated_P_INNER.args, **kwargs: Translated_P_INNER.kwargs) -> SUPERSELF" in src
    )
    assert "def aio(self, /, *args: Translated_P_INNER.args, **kwargs: Translated_P_INNER.kwargs) -> SUPERSELF" in src
    assert "meth: __meth_spec[Translated_P, typing_extensions.Self]" in src
    assert "def syncfunc(self) -> Translated_T:" in src


def test_synchronicity_generic_subclass():
    class Specific(MyGeneric[str]): ...

    assert Specific.__bases__ == (MyGeneric,)
    assert Specific.__orig_bases__ == (MyGeneric[str],)

    BlockingSpecific = synchronizer.create_blocking(Specific, "BlockingSpecific", __name__)
    assert BlockingSpecific.__bases__ == (BlockingMyGeneric,)
    assert BlockingSpecific.__orig_bases__ == (BlockingMyGeneric[str],)

    src = _class_source(BlockingSpecific)
    assert "class BlockingSpecific(BlockingMyGeneric[str]):" in src

    async def foo_impl(bar: MyGeneric[str]): ...

    foo = synchronizer.create_blocking(foo_impl, "foo")
    src = _function_source(foo)
    assert "def __call__(self, /, bar: BlockingMyGeneric[str]):" in src
    assert "async def aio(self, /, bar: BlockingMyGeneric[str]):" in src


_B = typing.TypeVar("_B", bound="str")

B = synchronizer.create_blocking(
    _B, "B", __name__
)  # only strictly needed if the bound is a synchronicity implementation type


def _ident(b: _B) -> _B:
    return b


ident = synchronizer.create_blocking(_ident, "ident", __name__)


def test_translated_bound_type_vars():
    emitter = StubEmitter(__name__)
    emitter.add_type_var(B, "B")
    emitter.add_function(ident, "ident")
    src = emitter.get_source()
    assert 'B = typing.TypeVar("B", bound="str")' in src
    assert "def ident(b: B) -> B" in src


def test_literal_alias(tmp_path):
    contents = dedent(
        """
        import typing
        from typing import Literal
        foo = typing.Literal["foo"]
        bar = Literal["bar"]
        """
    )
    with open(fname := (tmp_path / "foo.py"), "w") as f:
        f.write(contents)

    spec = importlib.util.spec_from_file_location("foo", fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    emitter = StubEmitter.from_module(mod)
    src = emitter.get_source()
    assert "foo = typing.Literal['foo']" in src
    assert "bar = typing.Literal['bar']" in src


def test_callable():
    def foo() -> collections.abc.Callable[[str], float]:
        return lambda x: 0.0

    src = _function_source(foo)
    assert "-> collections.abc.Callable[[str], float]" in src


def test_ellipsis():
    def foo() -> collections.abc.Callable[..., typing.Any]:
        return lambda x: 0

    src = _function_source(foo)
    assert "-> collections.abc.Callable[..., typing.Any]" in src


def test_param_spec():
    P = typing_extensions.ParamSpec("P")

    def foo() -> collections.abc.Callable[P, typing.Any]:
        return lambda x: 0

    src = _function_source(foo)
    assert "-> collections.abc.Callable[P, typing.Any]" in src


def test_typing_literal():
    def foo() -> typing.Literal["three", "str"]:
        return "str"

    src = _function_source(foo)
    assert "-> typing.Literal['three', 'str']" in src  # "str" should not be eval:ed in a Literal!


def test_overloads_unwrapped_functions():
    with overload_tracking.patched_overload():

        @typing.overload
        def _overloaded(arg: str) -> float: ...

        @typing.overload
        def _overloaded(arg: int) -> int: ...

        def _overloaded(arg: typing.Union[str, int]):
            if isinstance(arg, str):
                return float(arg)
            return arg

    overloaded = synchronizer.create_blocking(_overloaded, "overloaded")

    src = _function_source(overloaded)
    assert src.count("@typing.overload") == 2
    assert src.count("def overloaded") == 2  # original should be omitted
    assert "def overloaded(arg: str) -> float" in src
    assert "def overloaded(arg: int) -> int:" in src


# Patching `asynccontextmanager` to use `__annotate__` surfaces an issue with sigtools for generating stubs
@pytest.mark.skipif(sys.version_info[:2] == (3, 14), reason="asynccontextmanager does not work with Python 3.14")
def test_wrapped_context_manager_is_both_blocking_and_async():
    @asynccontextmanager
    async def foo(arg: int) -> typing.AsyncGenerator[str, None]:
        yield "hello"

    wrapped_foo = synchronizer.create_blocking(foo, name="wrapped_foo")
    assert wrapped_foo.__annotations__["return"] == typing.AsyncContextManager[str]
    wrapped_foo_src = _function_source(wrapped_foo)

    assert (
        "def __call__(self, /, arg: int) -> synchronicity.combined_types.AsyncAndBlockingContextManager[str]:"
        in wrapped_foo_src
    )
    assert "AbstractAsyncContextManager" not in wrapped_foo_src


@pytest.mark.skipif(sys.version_info < (3, 9), reason="collections.abc.Iterator isn't a generic type before Python 3.9")
def test_collections_iterator():
    def foo() -> collections.abc.Iterator[int]:
        class MyIterator(collections.abc.Iterator):
            def __iter__(self) -> collections.abc.Iterator[int]:
                return self

            def __next__(self) -> int:
                return 1

        return MyIterator()

    src = _function_source(foo)
    assert "-> collections.abc.Iterator[int]" in src


U = typing.TypeVar("U")


class _ReturnVal(typing.Generic[U]):
    pass


ReturnVal = synchronizer.create_blocking(_ReturnVal, "ReturnVal", __name__)


def test_returns_forward_wrapped_generic():
    # forward reference of a wrapped generic as a string is one of the trickier cases to handle
    # as the string needs to be evaluated, the generics need to be recursively expanded and
    # type vars need to be replaced with "inner" generated versions

    class _Container(typing.Generic[T]):
        async def fun(self) -> "ReturnVal[T]":
            return ReturnVal()

    Container = synchronizer.create_blocking(_Container, "Container")

    src = _class_source(Container)

    # base class should be generic in the (potentially) translated type var (could have wrapped bounds spec)
    assert "class Container(typing.Generic[Translated_T]):" in src
    assert "Translated_T_INNER = typing.TypeVar" in src  # distinct "inner copy" of Translated_T needs to be declared
    assert "typing_extensions.Protocol[Translated_T_INNER]" in src
    assert "def __call__(self, /) -> ReturnVal[Translated_T_INNER]:" in src
    assert "fun: __fun_spec[Translated_T]" in src


def custom_field():  # needs to be in global scope
    pass


def test_dataclass_transform():
    @typing_extensions.dataclass_transform(field_specifiers=(custom_field,), kw_only_default=True)
    def decorator():
        pass

    src = _function_source(decorator)
    assert "@typing_extensions.dataclass_transform(field_specifiers=(custom_field, ), kw_only_default=True, )\n" in src

    src = _function_source(decorator, target_module="other_module")
    assert "import test.type_stub_test" in src
    assert "import typing_extensions" in src
    assert "field_specifiers=(test.type_stub_test.custom_field, )" in src


def test_contextvar():
    import contextvars

    s = StubEmitter("blah")
    s.add_variable(contextvars.ContextVar, "c")
    src = s.get_source()
    assert "import contextvars" in src
    assert "c: contextvars.ContextVar" in src


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="collections.abc.Callable strips Concatenate wrappers at runtime before Python 3.10 :(",
)
def test_concatenate_origin_module():
    s = StubEmitter(__name__)
    P = typing_extensions.ParamSpec("P")
    R = typing.TypeVar("R")
    s.add_variable(collections.abc.Callable[typing_extensions.Concatenate[typing.Any, P], R], "f")
    src = s.get_source()
    print(src)
    assert "f: collections.abc.Callable[typing_extensions.Concatenate[typing.Any, P], R]" in src


def test_paramspec_args():
    from .type_stub_helpers.some_mod import P

    def foo(fn: collections.abc.Callable[P, None], *args: P.args, **kwargs: P.kwargs) -> str:
        return "Hello World!"

    src = _function_source(foo)
    assert "import test.type_stub_helpers.some_mod" in src
    assert (
        "def foo(fn: collections.abc.Callable[test.type_stub_helpers.some_mod.P, None], *args: test.type_stub_helpers.some_mod.P.args, **kwargs: test.type_stub_helpers.some_mod.P.kwargs) -> str:"  # noqa
        in src
    )  # noqa: E501


if typing.TYPE_CHECKING:
    import _typeshed


def test_typeshed():
    """Test that _typeshed annotations are preserved in stubs."""

    def foo() -> "_typeshed.OpenTextMode":
        return "r"

    src = _function_source(foo)
    assert "import _typeshed" in src
    assert "def foo() -> _typeshed.OpenTextMode:" in src


def test_positional_only_wrapped_function(synchronizer):
    @synchronizer.wrap
    async def f(pos_only=None, /, **kwargs): ...

    # The following used to crash because the injected `self` in the generated Protocol
    # didn't use the positional-only qualifier
    src = _function_source(f)
    assert "def __call__(self, pos_only=None, /, **kwargs):" in src


def test_docstrings():
    src = _function_source(single_line_docstring_func)
    assert '    """I have a single line docstring"""' in src

    src = _function_source(multi_line_docstring_func)
    assert '    """I have a docstring\n\n    with multiple lines\n    """\n' in src

    src = _function_source(nested_docstring_func)
    assert "'''I have a docstring" in src
    assert '"""SUPRISE! SO DO I!"""' in src

    src = _class_source(SingleLineDocstringClass)
    assert '    """I have a single line docstring"""\n' in src

    src = _class_source(MultiLineDocstringClass)
    assert '    """I have a docstring\n\n    with multiple lines\n    """\n' in src

    src = _class_source(ClassWithMethodsWithDocstrings)
    assert '        """I have a docstring"""\n' in src
    assert '        """I have a docstring\n\n        with multiple lines\n        """\n' in src

    with pytest.warns(UserWarning, match="both \"\"\" and ''' quote blocks"):
        src = _function_source(deranged_docstring_func)
        assert '"""' not in src


def test_pathlib():
    def test_path() -> pathlib.Path: ...

    src = _function_source(test_path)
    assert "import pathlib\n" in src
    assert "pathlib.Path" in src


@pytest.mark.skipif(sys.version_info < (3, 10), reason="Union type syntax (|) requires Python 3.10+")
def test_union_pipe_syntax_imports():
    """Test that Type | None syntax properly registers imports for Type.

    This is a regression test for a bug where Optional[Type] would correctly
    register imports for Type, but Type | None would not, because the PEP 604
    union syntax creates a types.UnionType which has __args__ but no __origin__.
    """

    # Create a mock external module type (simulating pandas.DataFrame)
    class MockDataFrame:
        pass

    MockDataFrame.__module__ = "pandas.core.frame"
    MockDataFrame.__name__ = "DataFrame"
    MockDataFrame.__qualname__ = "DataFrame"

    # Test 1: Optional syntax (baseline - this should work)
    def with_optional() -> typing.Optional[MockDataFrame]:
        pass

    src_optional = _function_source(with_optional)
    print("Optional syntax output:")
    print(src_optional)
    assert "import pandas.core.frame" in src_optional
    assert "pandas.core.frame.DataFrame" in src_optional

    # Test 2: Union | None syntax (the bug case)
    def with_union_pipe() -> MockDataFrame | None:
        pass

    src_union = _function_source(with_union_pipe)
    print("\nUnion | None syntax output:")
    print(src_union)
    assert "import pandas.core.frame" in src_union, "Type | None syntax should register imports for Type"
    assert "pandas.core.frame.DataFrame" in src_union

    # Test 3: More complex case - nested generics with union syntax
    def with_nested_union() -> typing.List[MockDataFrame | None]:
        pass

    src_nested = _function_source(with_nested_union)
    print("\nNested union syntax output:")
    print(src_nested)
    assert "import pandas.core.frame" in src_nested, "Nested Type | None should also register imports"
    assert "pandas.core.frame.DataFrame" in src_nested

    # Test 4: Union with multiple types from external modules
    class MockSeries:
        pass

    MockSeries.__module__ = "pandas.core.series"
    MockSeries.__name__ = "Series"
    MockSeries.__qualname__ = "Series"

    def with_multi_union() -> MockDataFrame | MockSeries | None:
        pass

    src_multi = _function_source(with_multi_union)
    print("\nMulti-type union syntax output:")
    print(src_multi)
    assert "import pandas.core.frame" in src_multi
    assert "import pandas.core.series" in src_multi
    assert "pandas.core.frame.DataFrame" in src_multi
    assert "pandas.core.series.Series" in src_multi


def test_async_classmethod_gets_aio(synchronizer):
    @synchronizer.wrap
    class A:
        @classmethod
        async def foo():
            pass

    src = _class_source(A, target_module=__name__)
    assert "__foo_spec" in src
    assert "foo: typing.ClassVar[__foo_spec" in src
    assert "async def aio(self" in src
    assert "def __call__(self" in src
