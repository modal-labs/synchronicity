import typing

import pytest

import synchronicity
from synchronicity import Interface
from synchronicity import async_wrap


class _Bar:
    pass

class _Foo:
    baz: _Bar
    async def bar(self, arg1: typing.AsyncIterator[str]):
        pass

    @async_wrap.asynccontextmanager  # tests the annotations-compatible context manager factory
    async def ctx(self) -> typing.AsyncGenerator[int, None]:
        yield 0

s = synchronicity.Synchronizer()
BlockingBar = s.create_blocking(_Bar, "BlockingBar")
AsyncBar = s.create_async(_Bar, "AsyncBar")
BlockingFoo = s.create_blocking(_Foo, "BlockingFoo")
AsyncFoo = s.create_async(_Foo, "AsyncFoo")

@pytest.mark.parametrize("t,interface,expected", [
    (typing.AsyncGenerator[int, str], Interface.BLOCKING, typing.Generator[int, str, None]),
    (typing.AsyncContextManager[_Foo], Interface.BLOCKING, typing.ContextManager[BlockingFoo]),
    (typing.AsyncContextManager[_Foo], Interface.ASYNC, typing.AsyncContextManager[AsyncFoo]),
    (typing.Awaitable[typing.Awaitable[str]], Interface.ASYNC, typing.Awaitable[typing.Awaitable[str]]),
    (typing.Awaitable[typing.Awaitable[str]], Interface.BLOCKING, str),
    (typing.AsyncIterable[str], Interface.BLOCKING, typing.Iterable[str]),
    (typing.AsyncIterator[str], Interface.BLOCKING, typing.Iterator[str]),
])
def test_annotation_mapping(t, interface, expected):
    assert s._map_type_annotation(t, interface) == expected


def test_wrapped_function_replaces_annotation():
    assert BlockingFoo.bar.__annotations__["arg1"] == typing.Iterator[str]
    assert BlockingFoo.__annotations__["baz"] == BlockingBar
    assert AsyncFoo.ctx.__annotations__["return"] == typing.AsyncContextManager[int]
    assert BlockingFoo.ctx.__annotations__["return"] == typing.ContextManager[int]
