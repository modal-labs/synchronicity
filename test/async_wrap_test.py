import inspect
import typing

from synchronicity import async_wrap


def test_wrap_corofunc_using_async():
    async def foo():
        pass

    @async_wrap.async_compat_wraps(foo)
    async def bar():
        pass

    assert inspect.iscoroutinefunction(bar)


def test_wrap_corofunc_using_non_async():
    async def foo():
        pass

    @async_wrap.async_compat_wraps(foo)
    def bar():
        pass

    assert inspect.iscoroutinefunction(bar)


def test_wrap_annotated_asyncgen_using_async():
    async def foo() -> typing.AsyncGenerator[str, typing.Any]:
        yield "bar"

    @async_wrap.async_compat_wraps(foo)
    async def bar():
        pass

    assert bar.__annotations__["return"] == typing.AsyncGenerator[str, typing.Any]
