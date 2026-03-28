import pytest
import typing
from inspect import get_annotations

from synchronicity import Synchronizer, combined_types
from synchronicity.interface import Interface
from synchronicity.type_stubs import StubEmitter


class ImplType:
    attr: str


synchronizer = Synchronizer()


@pytest.fixture(autouse=True, scope="module")
def synchronizer_teardown():
    yield
    synchronizer._close_loop()  # prevent "unclosed event loop" warnings


BlockingType = synchronizer.create_blocking(ImplType, "BlockingType", __name__)


def test_wrapped_class_keeps_class_annotations():
    assert get_annotations(BlockingType) == get_annotations(ImplType)


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
            combined_types.AsyncAndBlockingContextManager[BlockingType],
        ),
        (
            typing.AsyncContextManager[ImplType],
            Interface._ASYNC_WITH_BLOCKING_TYPES,
            typing.AsyncContextManager[BlockingType],
        ),
        (
            typing.Awaitable[typing.Awaitable[str]],
            Interface._ASYNC_WITH_BLOCKING_TYPES,
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
        (typing.Optional[ImplType], Interface._ASYNC_WITH_BLOCKING_TYPES, typing.Union[BlockingType, None]),
    ],
)
def test_annotation_mapping(t, interface, expected):
    stub_emitter = StubEmitter(__name__)
    assert stub_emitter._translate_annotation(t, synchronizer, interface, __name__) == expected
