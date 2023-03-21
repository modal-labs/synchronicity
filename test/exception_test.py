import asyncio
import concurrent
import inspect
import pytest
import time

from synchronicity import Synchronizer

SLEEP_DELAY = 0.1


class CustomException(Exception):
    pass


async def f_raises():
    await asyncio.sleep(0.1)
    raise CustomException("something failed")


def test_function_raises_sync():
    s = Synchronizer()
    t0 = time.time()
    with pytest.raises(CustomException):
        f_raises_s = s.create_blocking(f_raises)
        f_raises_s()
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


def test_function_raises_sync_futures():
    s = Synchronizer()
    t0 = time.time()
    f_raises_s = s.create_blocking(f_raises)
    fut = f_raises_s(_future=True)
    assert isinstance(fut, concurrent.futures.Future)
    assert time.time() - t0 < SLEEP_DELAY
    with pytest.raises(CustomException):
        fut.result()
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_function_raises_async():
    s = Synchronizer()
    t0 = time.time()
    f_raises_s = s.create_async(f_raises)
    coro = f_raises_s()
    assert inspect.iscoroutine(coro)
    assert time.time() - t0 < SLEEP_DELAY
    with pytest.raises(CustomException):
        await coro
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


async def f_raises_baseexc():
    await asyncio.sleep(0.1)
    raise KeyboardInterrupt


def test_function_raises_baseexc_sync():
    s = Synchronizer()
    t0 = time.time()
    with pytest.raises(BaseException):
        f_raises_baseexc_s = s.create_blocking(f_raises_baseexc)
        f_raises_baseexc_s()
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


def f_raises_syncwrap():
    return f_raises()  # returns a coro


@pytest.mark.asyncio
async def test_function_raises_async_syncwrap():
    s = Synchronizer()
    t0 = time.time()
    f_raises_syncwrap_s = s.create_async(f_raises_syncwrap)
    coro = f_raises_syncwrap_s()
    assert inspect.iscoroutine(coro)
    assert time.time() - t0 < SLEEP_DELAY
    with pytest.raises(CustomException):
        await coro
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY
