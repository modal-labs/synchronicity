import inspect
import typing

from synchronicity import async_wrap
from synchronicity.async_wrap import wraps_by_interface
from synchronicity.interface import Interface
from synchronicity.synchronizer import FunctionWithAio


def test_wrap_corofunc_using_async():
    async def foo():
        pass

    @wraps_by_interface(Interface._ASYNC_WITH_BLOCKING_TYPES, foo)
    async def bar():
        pass

    assert inspect.iscoroutinefunction(bar)


def test_wrap_corofunc_using_non_async():
    async def foo():
        pass

    @wraps_by_interface(Interface._ASYNC_WITH_BLOCKING_TYPES, foo)
    def bar():
        pass

    assert inspect.iscoroutinefunction(bar)


def test_wrap_asynccontextmanager_annotations():
    @async_wrap.asynccontextmanager  # this would not work with contextlib.asynccontextmanager
    async def foo() -> typing.AsyncGenerator[int, None]: ...

    assert foo.__annotations__["return"] == typing.AsyncContextManager[int]


def test_wrap_staticmethod(synchronizer):
    class Foo:
        @staticmethod
        async def a_static_method() -> typing.Awaitable[str]:
            async def wrapped():
                return "hello"

            return wrapped()

    BlockingFoo = synchronizer.create_blocking(Foo)

    assert isinstance(BlockingFoo.__dict__["a_static_method"], FunctionWithAio)
    assert not inspect.iscoroutinefunction(BlockingFoo.__dict__["a_static_method"]._func)
    assert inspect.iscoroutinefunction(BlockingFoo.__dict__["a_static_method"].aio)
