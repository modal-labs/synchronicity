import asyncio
import inspect
import pytest
import time

from synchronicity import Interface, Synchronizer, constructor


def gen_classes():
    s = Synchronizer()

    class Foo:
        @constructor(Interface.BLOCKING)
        async def create_blocking(self, x):
            """Do the blocking magic"""
            await asyncio.sleep(0.1)
            self._x = x

        @constructor(Interface.ASYNC)
        def create_async(self, x):
            """Do the async magic"""
            self._x = x + 7

        @property
        def x(self):
            return self._x

    classes = s.create(Foo)
    return (
        Foo,
        classes[Interface.BLOCKING],
        classes[Interface.ASYNC],
    )


def test_async_constructor():
    Foo, BlockingFoo, AsyncFoo = gen_classes()

    # Try using the blocking interface
    t0 = time.time()
    foo = BlockingFoo(42)
    assert 0.09 <= time.time() - t0 <= 0.11
    assert isinstance(foo, BlockingFoo)
    assert foo.x == 42

    # Try using the async interface
    t0 = time.time()
    foo = AsyncFoo(42)
    assert time.time() - t0 < 0.01
    assert foo.x == 49

    # Check docstrings
    assert BlockingFoo.__init__.__doc__ == "Do the blocking magic"
    assert AsyncFoo.__init__.__doc__ == "Do the async magic"
