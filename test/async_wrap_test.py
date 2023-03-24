import inspect
import typing

import synchronicity
from synchronicity import Interface

synchronizer = synchronicity.Synchronizer()

def test_wrap_corofunc_using_async():
    async def foo():
        pass

    @synchronizer.wraps_by_interface(Interface.ASYNC, foo)
    async def bar():
        pass

    assert inspect.iscoroutinefunction(bar)


def test_wrap_corofunc_using_non_async():
    async def foo():
        pass

    @synchronizer.wraps_by_interface(Interface.ASYNC, foo)
    def bar():
        pass

    assert inspect.iscoroutinefunction(bar)


def test_wrap_annotated_asyncgen_using_async():
    async def foo() -> typing.AsyncGenerator[str, typing.Any]:
        yield "bar"

    @synchronizer.wraps_by_interface(Interface.ASYNC, foo)
    async def bar():
        pass

    # note that we do no explicit
    assert bar.__annotations__["return"] == typing.AsyncGenerator[str, typing.Any]


def test_wrap_staticmethod():
    class Foo:
        @staticmethod
        async def a_static_method() -> typing.Awaitable[str]:
            async def wrapped():
                return "hello"
            return wrapped()

    BlockingFoo = synchronizer.create_blocking(Foo)
    AsyncFoo = synchronizer.create_async(Foo)

    assert isinstance(BlockingFoo.__dict__["a_static_method"], staticmethod)
    assert isinstance(AsyncFoo.__dict__["a_static_method"], staticmethod)

    assert BlockingFoo.a_static_method.__annotations__["return"] == str
    assert AsyncFoo.a_static_method.__annotations__["return"] == typing.Awaitable[str]
    assert inspect.iscoroutinefunction(AsyncFoo.__dict__["a_static_method"].__func__)
    assert not inspect.iscoroutinefunction(BlockingFoo.__dict__["a_static_method"].__func__)
