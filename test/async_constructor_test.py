import asyncio
import inspect
import pytest
import time

from synchronicity import Interface, Synchronizer


def test_async_constructor():
    class Foo:
        async def __init__(self):
            await asyncio.sleep(0.1)

    s = Synchronizer()

    # Try using the blocking interface
    BlockingFoo = s.create(Foo)[Interface.BLOCKING]
    t0 = time.time()
    foo = BlockingFoo()
    assert 0.09 <= time.time() - t0 <= 0.11
    assert isinstance(foo, BlockingFoo)

    # Try using the async interface
    AsyncFoo = s.create(Foo)[Interface.ASYNC]
    foo = AsyncFoo()
    assert inspect.iscoroutine(foo)

    # Make sure resolving the coroutine results in an object
    t0 = time.time()
    loop = asyncio.get_event_loop()
    foo = loop.run_until_complete(foo)
    assert 0.09 <= time.time() - t0 <= 0.11
    assert isinstance(foo, AsyncFoo)


def test_sync_constructor():
    class Foo:
        def __init__(self):
            pass

    s = Synchronizer()
    BlockingFoo = s.create(Foo)[Interface.BLOCKING]
    t0 = time.time()
    foo = BlockingFoo()
    assert isinstance(foo, BlockingFoo)
