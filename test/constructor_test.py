import asyncio
import inspect
import pytest
import time

from synchronicity import Interface, Synchronizer, constructor


def test_async_constructor():
    s = Synchronizer()

    class Foo:
        @constructor()
        def __init__(self, x):
            self._x = x

        @constructor(Interface.BLOCKING)
        async def create_blocking(self, x):
            """Do the blocking magic"""
            await asyncio.sleep(0.1)
            self._x = x + 3

        @constructor(Interface.ASYNC)
        def create_async(self, x):
            """Do the async magic"""
            self._x = x + 7

        @property
        def x(self):
            return self._x

    Foo_classes = s.create(Foo)
    BlockingFoo = Foo_classes[Interface.BLOCKING]
    AsyncFoo = Foo_classes[Interface.ASYNC]

    # Try using the blocking interface
    t0 = time.time()
    foo = BlockingFoo(42)
    assert isinstance(foo, BlockingFoo)
    assert 0.09 <= time.time() - t0 <= 0.11
    assert foo.x == 45

    # Try using the async interface
    t0 = time.time()
    foo = AsyncFoo(42)
    assert isinstance(foo, AsyncFoo)
    assert time.time() - t0 < 0.01
    assert foo.x == 49

    # Check docstrings
    assert BlockingFoo.__init__.__doc__ == "Do the blocking magic"
    assert AsyncFoo.__init__.__doc__ == "Do the async magic"

    # Try a subclass that inherits

    class Bar(Foo):
        pass

    Bar_classes = s.create(Bar)
    BlockingBar = Bar_classes[Interface.BLOCKING]
    AsyncBar = Bar_classes[Interface.ASYNC]
    bar = BlockingBar(42)
    assert isinstance(bar, BlockingBar)
    assert bar.x == 45
    bar = AsyncBar(42)
    assert isinstance(bar, AsyncBar)
    assert bar.x == 49

    # Try a subclass that uses to the superconstructor

    class Baz(Bar):
        @constructor(Interface.BLOCKING, Interface.ASYNC)
        def create(self, x, y):
            super().__init__(x + y)

    Baz_classes = s.create(Baz)
    BlockingBaz = Baz_classes[Interface.BLOCKING]
    AsyncBaz = Baz_classes[Interface.ASYNC]
    baz = BlockingBaz(10, 20)
    assert isinstance(baz, BlockingBaz)
    assert baz.x == 30
    baz = AsyncBaz(20, 30)
    assert isinstance(baz, AsyncBaz)
    assert baz.x == 50
