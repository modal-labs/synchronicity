import inspect
import typing

import synchronicity
from synchronicity import async_wrap, Interface

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
