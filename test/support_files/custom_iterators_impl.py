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
    # iterat*ors* are single use
    def __init__(self, items: list[int]):
        self.items: list[int] = items

    def __aiter__(self) -> typing.Self:
        return self  # return self reference in case of `for ... in ...`

    async def __anext__(self) -> int:
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
    yield 1
    yield 2
