import functools
import typing

import synchronicity
from synchronicity import Synchronizer
from synchronicity.genstub import StubEmitter


def test_module_assignment():
    s = Synchronizer()

    class Foo:
        pass

    BFoo = s.create_blocking(Foo, "BFoo", "mymod")
    assert s._target_modules == {"mymod": {"BFoo": BFoo}}


def noop():
    pass


def arg_no_anno(arg1):
    pass


def scalar_args(arg1: str, arg2: int) -> float:
    pass


from .genstub_helpers import some_mod


def generic_other_module_arg(arg: typing.List[some_mod.Foo]):
    pass


async def async_func() -> str:
    return "hello"


async def async_gen() -> typing.AsyncGenerator[int, None]:
    yield 0


def weird_async_gen() -> typing.AsyncGenerator[int, None]:
    # non-async function that returns an async generator
    async def gen():
        yield 0

    return gen()


def _function_source(func, strip_mod=False):
    stub_emitter = StubEmitter("dummy" if not strip_mod else func.__module__)
    stub_emitter.add_function(func, func.__name__)
    return stub_emitter.get_source()


def _class_source(cls, strip_mod=False):
    stub_emitter = StubEmitter("dummy" if not strip_mod else cls.__module__)
    stub_emitter.add_class(cls, cls.__name__)
    return stub_emitter.get_source()


def test_function_basics():
    assert _function_source(noop) == "def noop():\n    ...\n"
    assert _function_source(arg_no_anno) == "def arg_no_anno(arg1):\n    ...\n"
    assert (
        _function_source(scalar_args)
        == "def scalar_args(arg1: str, arg2: int) -> float:\n    ...\n"
    )


def test_function_with_imports():
    assert (
        _function_source(generic_other_module_arg)
        == """import test.genstub_helpers.some_mod
import typing

def generic_other_module_arg(arg: typing.List[test.genstub_helpers.some_mod.Foo]):
    ...
"""
    )


def test_async_func():
    assert _function_source(async_func) == "async def async_func() -> str:\n    ...\n"


def test_async_gen():
    assert (
        _function_source(async_gen)
        == "import typing\n\nasync def async_gen() -> typing.AsyncGenerator[int, None]:\n    ...\n"
    )
    assert (
        _function_source(weird_async_gen)
        == "import typing\n\ndef weird_async_gen() -> typing.AsyncGenerator[int, None]:\n    ...\n"
    )


class Foo:
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


def test_class_generation():
    emitter = StubEmitter("mod")
    emitter.add_class(Foo, "Foo")
    source = emitter.get_source()

    assert (
        source
        == """class Foo:
    class_var: str
    def some_method(self) -> bool:
        ...

    @classmethod
    def some_class_method(cls) -> int:
        ...

    @staticmethod
    def some_staticmethod() -> float:
        ...

    @property
    def some_property(self) -> str:
        ...
"""
    )


def merged_signature(*sigs):
    sig = sigs[0].copy()
    return sig


def test_wrapped_function_with_new_annotations():
    """A wrapped function (in general, using functools.wraps/partial) would
    have an inspect.signature from the wrapped function by default
    and from the wrapper function is inspect.signature gets the follow_wrapped=True
    option. However, for the best type stub usability, the best would be to combine
    all layers of wrapping, adding any additional arguments or annotations as updates
    to the underlying wrapped function signature.

    This test makes sure we do just that.
    """

    def orig(arg: str):
        pass

    @functools.wraps(orig)
    def wrapper(extra_arg: int, *args, **kwargs):
        orig(*args, **kwargs)

    wrapper.__annotations__.update({"extra_arg": int, "arg": float})
    assert (
        _function_source(wrapper) == "def orig(extra_arg: int, arg: float):\n    ...\n"
    )


def test_base_class_included_and_imported():
    class Foo:
        def base(self) -> str:
            pass

    Foo.__module__ = "foomod"
    Foo.__qualname__ = "Foo"

    class Bar(Foo):
        def sub(self) -> float:
            pass

    src = _class_source(Bar, strip_mod=True)

    assert "import foomod" in src
    assert "class Bar(foomod.Foo):" in src
    assert "base" not in src


def test_typevar():
    T = typing.TypeVar("T")
    T.__module__ = "source_mod"

    def foo(arg: T) -> T:
        pass

    src = _function_source(foo)
    assert "import source_mod" in src
    assert "def foo(arg: source_mod.T) -> source_mod.T" in src


def test_string_annotation():
    stub_emitter = StubEmitter("dummy")
    stub_emitter.add_variable(annotation="Foo", name="some_foo")  # string annotation
    src = stub_emitter.get_source()
    assert 'some_foo: "Foo"' in src or "some_foo: 'Foo'" in src


def test_forward_ref():
    class Foo:
        def foo(self) -> "Bar":
            pass

    class Bar:
        pass

    # add in the same order here:
    stub = StubEmitter(__name__)
    stub.add_class(Foo, "Foo")
    stub.add_class(Bar, "Bar")
    src = stub.get_source()
    assert "class Bar:" in src
    assert "def foo(self) -> 'Bar':" in src


def test_self_ref():
    class Foo:
        def foo(self) -> "Foo":
            pass

    src = _class_source(Foo, strip_mod=True)
    assert "def foo(self) -> 'Foo'" in src


def test_synchronicity_type_translation():
    class _Foo:
        pass

    async def get_foo() -> _Foo:
        pass

    synchronizer = synchronicity.Synchronizer()
    Foo = synchronizer.create_blocking(_Foo, "Foo", __name__)
    get_foo = synchronizer.create_blocking(get_foo, "get_foo", __name__)

    src = _function_source(get_foo, strip_mod=True)
    assert "def get_foo() -> Foo" in src


def test_synchronicity_self_ref():
    class _Foo:
        @staticmethod
        async def foo() -> "_Foo":
            pass

    synchronizer = synchronicity.Synchronizer()
    Foo = synchronizer.create_blocking(_Foo, "Foo", __name__)

    src = _class_source(Foo, strip_mod=True)
    assert "@staticmethod" in src
    assert "    def foo() -> '_Foo'" in src  # TODO: this should return 'Foo' (!)


def test_custom_generic():
    T = typing.TypeVar("T")

    class MyGeneric(typing.Generic[T]):
        pass

    src = _class_source(MyGeneric, strip_mod=True)

    assert "class MyGeneric(typing.Generic[T]):" in src
