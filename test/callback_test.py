import asyncio
import pytest
import time


def sleep(ms):
    time.sleep(ms / 1000)
    return ms


async def sleep_async(ms):
    time.sleep(ms / 1000)
    return ms


@pytest.mark.asyncio
async def test_blocking(synchronizer):
    sleep_cb = synchronizer.create_callback(sleep)
    t0 = time.time()
    coros = [sleep_cb(200), sleep_cb(300), sleep_cb(300), sleep_cb(300)]
    rets = await asyncio.gather(*coros)
    assert rets == [200, 300, 300, 300]
    assert 0.3 <= time.time() - t0 < 0.5  # make sure they run in parallel


@pytest.mark.asyncio
async def test_async(synchronizer):
    sleep_cb = synchronizer.create_callback(sleep_async)
    t0 = time.time()
    coros = [sleep_cb(200), sleep_cb(300), sleep_cb(300), sleep_cb(300)]
    rets = await asyncio.gather(*coros)
    assert rets == [200, 300, 300, 300]
    assert 0.3 <= time.time() - t0 <= 0.5


@pytest.mark.asyncio
async def test_translate(synchronizer):
    class Foo:
        def __init__(self, x):
            self.x = x

        def get(self):
            return self.x

    BlockingFoo = synchronizer.create_blocking(Foo)

    def f(foo):
        assert isinstance(foo, BlockingFoo)
        x = foo.get()
        return BlockingFoo(x + 1)

    f_cb = synchronizer.create_callback(f)

    foo1 = Foo(42)
    foo2 = await f_cb(foo1)
    assert foo2.x == 43
