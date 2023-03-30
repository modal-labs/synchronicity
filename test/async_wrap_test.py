import inspect
import typing

import synchronicity
from synchronicity import Interface, async_wrap
from synchronicity.async_wrap import wraps_by_interface


def test_wrap_corofunc_using_async():
    async def foo():
        pass

    @wraps_by_interface(Interface.ASYNC, foo)
    async def bar():
        pass

    assert inspect.iscoroutinefunction(bar)


def test_wrap_corofunc_using_non_async():
    async def foo():
        pass

    @wraps_by_interface(Interface.ASYNC, foo)
    def bar():
        pass

    assert inspect.iscoroutinefunction(bar)


def test_wrap_asynccontextmanager_annotations():
    @async_wrap.asynccontextmanager  # this would not work with contextlib.asynccontextmanager
    async def foo() -> typing.AsyncGenerator[int, None]:
        pass

    assert foo.__annotations__["return"] == typing.AsyncContextManager[int]


def test_wrap_staticmethod():
    class Foo:
        @staticmethod
        async def a_static_method() -> typing.Awaitable[str]:
            async def wrapped():
                return "hello"

            return wrapped()

    synchronizer = synchronicity.Synchronizer()
    BlockingFoo = synchronizer.create_blocking(Foo)
    AsyncFoo = synchronizer.create_async(Foo)

    assert isinstance(BlockingFoo.__dict__["a_static_method"], staticmethod)
    assert isinstance(AsyncFoo.__dict__["a_static_method"], staticmethod)

    assert inspect.iscoroutinefunction(AsyncFoo.__dict__["a_static_method"].__func__)
    assert not inspect.iscoroutinefunction(
        BlockingFoo.__dict__["a_static_method"].__func__
    )
