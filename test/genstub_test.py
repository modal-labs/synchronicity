import typing

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


def _function_source(func):
    stub_emitter = StubEmitter("dummy")
    stub_emitter.add_function(func, func.__name__)
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
    emitter.add_class(Foo)
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


def test_base_classes():
    # TODO: make classes include their base classes as imports/references in the type stub
    pass
