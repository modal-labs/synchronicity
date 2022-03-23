import asyncio
import pytest
import time

from synchronicity import Interface, Synchronizer


def sleep(t):
    time.sleep(t)
    return t


async def sleep_async(t):
    time.sleep(t)
    return t


@pytest.mark.asyncio
async def test_blocking():
    s = Synchronizer()
    sleep_cb = s.create_callback(Interface.BLOCKING, sleep)
    t0 = time.time()
    coros = [sleep_cb(i * 0.01) for i in range(1, 11)]
    assert len(coros) == 10
    rets = await asyncio.gather(*coros)
    assert 0.095 <= time.time() - t0 <= 0.105


@pytest.mark.asyncio
async def test_async():
    s = Synchronizer()
    sleep_cb = s.create_callback(Interface.ASYNC, sleep_async)
    t0 = time.time()
    coros = [sleep_cb(i * 0.01) for i in range(1, 11)]
    assert len(coros) == 10
    rets = await asyncio.gather(*coros)
    assert 0.095 <= time.time() - t0 <= 0.105
