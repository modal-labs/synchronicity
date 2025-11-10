import threading
import typing

import synchronicity

mod = synchronicity.Module("custom_iterators")


@mod.wrap_class
class CustomAsyncIterable:
    # iterables are supposed to be callable multiple times
    def __aiter__(self) -> typing.AsyncIterator[int]:
        return CustomAsyncIterator([1, 2, 3])


@mod.wrap_class
class CustomAsyncIterator:
    num_iters: int

    # iterat*ors* are typically "single use", and have their __iter__/__aiter__
    # just return self
    def __init__(self, items: list[int]):
        self.items: list[int] = items
        self.num_iters = 0

    def __aiter__(self) -> typing.Self:
        self.num_iters += 1
        return self  # return self reference in case of `for ... in ...`

    async def __anext__(self) -> int:
        assert threading.current_thread().ident != threading.main_thread().ident
        if len(self.items):
            return self.items.pop(0)
        raise StopAsyncIteration()


@mod.wrap_function
def get_iterable() -> typing.AsyncIterable[int]:
    return CustomAsyncIterable()


@mod.wrap_function
def get_iterator() -> typing.AsyncIterator[int]:
    return CustomAsyncIterator([1, 2, 3])


@mod.wrap_function
async def generator_as_iterator() -> typing.AsyncIterator[int]:
    assert threading.current_thread().ident != threading.main_thread().ident
    yield 1
    yield 2


@mod.wrap_class
class IterableClassUsingGenerator:
    async def __aiter__(self):
        assert threading.current_thread().ident != threading.main_thread().ident
        yield 1
        yield 2


@mod.wrap_class
class IterableClassUsingGeneratorTyped:
    async def __aiter__(self) -> typing.AsyncGenerator[int]:
        assert threading.current_thread().ident != threading.main_thread().ident
        yield 1
        yield 2
