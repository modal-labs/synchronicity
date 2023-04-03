import typing

import pytest

import synchronicity
from synchronicity import Interface, Synchronizer
from synchronicity.type_stubs import StubEmitter


class ImplType:
    attr: str


synchronizer = Synchronizer()

BlockingType = synchronizer.create_blocking(ImplType, "BlockingType", __name__)
AsyncType = synchronizer.create_async(ImplType, "AsyncType", __name__)


def test_wrapped_class_keeps_class_annotations():
    assert BlockingType.__annotations__ == ImplType.__annotations__
    assert AsyncType.__annotations__ == AsyncType.__annotations__


@pytest.mark.parametrize(
    "t,interface,expected",
    [
        (
            typing.AsyncGenerator[int, str],
            Interface.BLOCKING,
            typing.Generator[int, str, None],
        ),
        (
            typing.AsyncContextManager[ImplType],
            Interface.BLOCKING,
            typing.ContextManager[BlockingType],
        ),
        (
            typing.AsyncContextManager[ImplType],
            Interface.ASYNC,
            typing.AsyncContextManager[AsyncType],
        ),
        (
            typing.Awaitable[typing.Awaitable[str]],
            Interface.ASYNC,
            typing.Awaitable[typing.Awaitable[str]],
        ),
        (typing.Awaitable[typing.Awaitable[str]], Interface.BLOCKING, str),
        (typing.Coroutine[None, None, str], Interface.BLOCKING, str),
        (typing.AsyncIterable[str], Interface.BLOCKING, typing.Iterable[str]),
        (typing.AsyncIterator[str], Interface.BLOCKING, typing.Iterator[str]),
        (
            typing.Optional[ImplType],
            Interface.BLOCKING,
            typing.Union[BlockingType, None],
        ),
        (typing.Optional[ImplType], Interface.ASYNC, typing.Union[AsyncType, None]),
    ],
)
def test_annotation_mapping(t, interface, expected):
    stub_emitter = StubEmitter(__name__)
    assert (
        stub_emitter._translate_annotation(t, synchronizer, interface, __name__)
        == expected
    )
