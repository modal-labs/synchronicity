"""Consumer typing checks for generated simple_class wrappers."""

from typing import assert_type

import simple_class


def _sync_usage() -> None:
    counter = simple_class.Counter(10)
    assert_type(counter, simple_class.Counter)
    v = counter.increment()
    assert_type(v, int)
    assert list(counter.get_multiples(3)) == [0, 11, 22]
    assert_type(counter.sync_method(), int)


async def _async_usage() -> None:
    counter = simple_class.Counter(5)
    r = await counter.increment.aio()
    assert_type(r, int)
    out: list[int] = []
    async for val in counter.get_multiples.aio(3):
        out.append(val)
    assert out == [0, 6, 12]
