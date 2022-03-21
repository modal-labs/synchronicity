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
    # It should fail since the function returns a coroutine
    AsyncFoo = s.create(Foo)[Interface.ASYNC]
    with pytest.raises(RuntimeError):
        foo = AsyncFoo()


def test_sync_constructor():
    class Foo:
        def __init__(self):
            pass

    s = Synchronizer()

    # Try the blocking interface
    BlockingFoo = s.create(Foo)[Interface.BLOCKING]
    foo = BlockingFoo()
    assert isinstance(foo, BlockingFoo)

    # Try the async interface
    AsyncFoo = s.create(Foo)[Interface.ASYNC]
    foo = AsyncFoo()
    assert isinstance(foo, AsyncFoo)
