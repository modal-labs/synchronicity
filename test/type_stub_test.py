import functools
import typing

import synchronicity
from synchronicity import overload_tracking
from synchronicity.type_stubs import StubEmitter


def noop():
    pass


def arg_no_anno(arg1):
    pass


def scalar_args(arg1: str, arg2: int) -> float:
    pass


from .type_stub_helpers import some_mod


def generic_other_module_arg(arg: typing.List[some_mod.Foo]):
    pass


async def async_func() -> str:
    return "hello"


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
    assert (
        _function_source(scalar_args)
        == "def scalar_args(arg1: str, arg2: int) -> float:\n    ...\n"
    )


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
    # since the yield keyword is removed in a type stub, the async prefix needs to be removed as well to avoid "double asyncness" (while keeping the remaining annotation)
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
    assert_in_after_last("class MixedClass:")
    assert_in_after_last(f"{indent}class_var: str")
    assert_in_after_last(f"{indent}class_var: str")
    assert_in_after_last(f"{indent}def some_method(self) -> bool:\n{indent * 2}...")
    assert_in_after_last(
        f"{indent}@classmethod\n{indent}def some_class_method(cls) -> int:\n{indent * 2}..."
    )
    assert_in_after_last(
        f"{indent}@staticmethod\n{indent}def some_staticmethod() -> float:"
    )
    assert_in_after_last(f"{indent}@property\n{indent}def some_property(self) -> str:")


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


class Base:
    def base_method(self) -> str:
        pass


Base.__module__ = "basemod"
Base.__qualname__ = "Base"


class Based(Base):
    def sub(self) -> float:
        pass


def test_base_class_included_and_imported():
    src = _class_source(Based)
    assert "import basemod" in src
    assert "class Based(basemod.Base):" in src
    assert "base_method" not in src  # base class method should not be in emitted stub


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


class Forwarder:
    def foo(self) -> typing.Optional["Forwardee"]:
        pass


class Forwardee:
    pass


def test_forward_ref():
    # add in the same order here:
    stub = StubEmitter(__name__)
    stub.add_class(Forwarder, "Forwarder")
    stub.add_class(Forwardee, "Forwardee")
    src = stub.get_source()
    assert "class Forwarder:" in src
    assert (
        "def foo(self) -> typing.Union[Forwardee, None]:" in src
    )  # should technically be 'Forwardee', but non-strings seem ok in pure type stubs


class SelfRefFoo:
    def foo(self) -> "SelfRefFoo":
        pass


def test_self_ref():
    src = _class_source(SelfRefFoo)
    assert (
        "def foo(self) -> SelfRefFoo" in src
    )  # should technically be 'Foo' but non-strings seem ok in pure type stubs


class _Foo:
    @staticmethod
    async def clone(foo: "_Foo") -> "_Foo":
        pass


synchronizer = synchronicity.Synchronizer()
Foo = synchronizer.create_blocking(_Foo, "Foo", __name__)


def test_synchronicity_type_translation():
    async def _get_foo() -> _Foo:
        pass

    get_foo = synchronizer.create_blocking(_get_foo, "get_foo", __name__)
    src = _function_source(get_foo)
    assert "def get_foo() -> Foo" in src


def test_synchronicity_self_ref():
    src = _class_source(Foo)
    assert "@staticmethod" in src
    assert "    def clone(foo: Foo) -> Foo" in src


class _WithClassMethod:
    @classmethod
    def classy(cls):
        pass


WithClassMethod = synchronizer.create_blocking(
    _WithClassMethod, "WithClassMethod", __name__
)


def test_synchronicity_classmethod():
    src = _class_source(WithClassMethod)
    assert "@classmethod" in src
    assert "    def classy(cls):" in src


T = typing.TypeVar("T")


class MyGeneric(typing.Generic[T]):
    pass


BlockingGeneric = synchronizer.create_blocking(
    typing.Generic, "BlockingGeneric", __name__
)
BlockingMyGeneric = synchronizer.create_blocking(
    MyGeneric,
    "BlockingMyGeneric",
    __name__,
)


def test_custom_generic():
    # TODO: build out this test a bit, as it currently creates an invalid stub (missing base types)
    class Specific(MyGeneric[str]):
        pass

    src = _class_source(Specific)
    assert "class Specific(MyGeneric[str]):" in src


def test_synchronicity_generic_subclass():
    class Specific(MyGeneric[str]):
        pass

    assert Specific.__bases__ == (MyGeneric,)
    assert Specific.__orig_bases__ == (MyGeneric[str],)

    BlockingSpecific = synchronizer.create_blocking(
        Specific, "BlockingSpecific", __name__
    )
    src = _class_source(BlockingSpecific)
    assert "class BlockingSpecific(BlockingMyGeneric[str]):" in src

    async def foo_impl(bar: MyGeneric[str]):
        pass

    foo = synchronizer.create_blocking(foo_impl, "foo")
    src = _function_source(foo)
    assert "def foo(bar: BlockingMyGeneric[str]):" in src


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


def test_ellipsis():
    def foo() -> typing.Callable[..., typing.Any]:
        pass

    src = _function_source(foo)
    assert "-> typing.Callable[..., typing.Any]" in src


def test_overloads_unwrapped_functions():
    with overload_tracking.patched_overload():

        @typing.overload
        def _overloaded(arg: str) -> float:
            pass

        @typing.overload
        def _overloaded(arg: int) -> int:
            pass

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
