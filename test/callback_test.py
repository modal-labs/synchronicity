import asyncio
import pytest
import time

from synchronicity import Interface, Synchronizer


def sleep(ms):
    time.sleep(ms / 1000)
    return ms


async def sleep_async(ms):
    time.sleep(ms / 1000)
    return ms


@pytest.mark.asyncio
async def test_blocking():
    s = Synchronizer()
    sleep_cb = s.create_callback(Interface.BLOCKING, sleep)
    t0 = time.time()
    coros = [sleep_cb(200), sleep_cb(300)]
    rets = await asyncio.gather(*coros)
    assert rets == [200, 300]
    assert 0.3 <= time.time() - t0 <= 0.4  # make sure they run in parallel


@pytest.mark.asyncio
async def test_async():
    s = Synchronizer()
    sleep_cb = s.create_callback(Interface.ASYNC, sleep_async)
    t0 = time.time()
    coros = [sleep_cb(200), sleep_cb(300)]
    rets = await asyncio.gather(*coros)
    assert rets == [200, 300]
    assert 0.3 <= time.time() - t0 <= 0.4
