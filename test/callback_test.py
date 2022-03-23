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
    coros = [sleep_cb(0.2), sleep_cb(0.3)]
    rets = await asyncio.gather(*coros)
    assert 0.3 <= time.time() - t0 <= 0.4  # make sure they run in parallel


@pytest.mark.asyncio
async def test_async():
    s = Synchronizer()
    sleep_cb = s.create_callback(Interface.ASYNC, sleep_async)
    t0 = time.time()
    coros = [sleep_cb(0.2), sleep_cb(0.3)]
    rets = await asyncio.gather(*coros)
    assert 0.3 <= time.time() - t0 <= 0.4
