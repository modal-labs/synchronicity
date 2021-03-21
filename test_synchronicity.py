import asyncio
import concurrent.futures
import inspect
import pytest
import time

from synchronicity import Synchronizer

SLEEP_DELAY = 0.1


async def f(x):
    await asyncio.sleep(0.1)
    return x**2


def test_function_sync():
    s = Synchronizer()
    t0 = time.time()
    fut = s(f)(42)
    assert isinstance(fut, concurrent.futures.Future)
    assert time.time() - t0 < SLEEP_DELAY
    assert fut.result() == 1764
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_function_async():
    s = Synchronizer()
    t0 = time.time()
    coro = s(f)(42)
    assert inspect.iscoroutine(coro)
    assert time.time() - t0 < SLEEP_DELAY
    assert await coro == 1764
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


def test_function_many_parallel_sync():
    s = Synchronizer()
    g = s(f)
    t0 = time.time()
    futs = [g(i) for i in range(1000)]
    assert isinstance(futs[0], concurrent.futures.Future)
    assert time.time() - t0 < SLEEP_DELAY
    assert [fut.result() for fut in futs] == [z**2 for z in range(1000)]
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_function_many_paralel_async():
    s = Synchronizer()
    g = s(f)
    t0 = time.time()
    coros = [g(i) for i in range(1000)]
    assert inspect.iscoroutine(coros[0])
    assert time.time() - t0 < SLEEP_DELAY
    assert await asyncio.gather(*coros) == [z**2 for z in range(1000)]
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


class CustomException(Exception):
    pass


async def f_raises():
    await asyncio.sleep(0.1)
    raise CustomException('something failed')


def test_function_raises_sync():
    s = Synchronizer()
    t0 = time.time()
    fut = s(f_raises)()
    assert isinstance(fut, concurrent.futures.Future)
    assert time.time() - t0 < SLEEP_DELAY
    with pytest.raises(CustomException):
        fut.result()
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_function_raises_async():
    s = Synchronizer()
    t0 = time.time()
    coro = s(f_raises)()
    assert inspect.iscoroutine(coro)
    assert time.time() - t0 < SLEEP_DELAY
    with pytest.raises(CustomException):
        await coro
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


async def gen(n):
    for i in range(n):
        await asyncio.sleep(0.1)
        yield i


def test_generator_sync():
    s = Synchronizer()
    t0 = time.time()
    it = s(gen)(3)
    assert inspect.isgenerator(it)
    assert time.time() - t0 < SLEEP_DELAY
    l = list(it)
    assert l == [0, 1, 2]
    assert time.time() - t0 > len(l) * SLEEP_DELAY


@pytest.mark.asyncio
async def test_generator_async():
    s = Synchronizer()
    t0 = time.time()
    asyncgen = s(gen)(3)
    assert inspect.isasyncgen(asyncgen)
    assert time.time() - t0 < SLEEP_DELAY
    l = [z async for z in asyncgen]
    assert l== [0, 1, 2]
    assert time.time() - t0 > len(l) * SLEEP_DELAY



def test_sync_lambda_returning_coroutine_sync():
    s = Synchronizer()
    t0 = time.time()
    g = s(lambda z: f(z + 1))
    fut = g(42)
    assert isinstance(fut, concurrent.futures.Future)
    assert time.time() - t0 < SLEEP_DELAY
    assert fut.result() == 1849
    assert time.time() - t0 > SLEEP_DELAY


@pytest.mark.asyncio
async def test_sync_lambda_returning_coroutine_async():
    s = Synchronizer()
    t0 = time.time()
    g = s(lambda z: f(z + 1))
    coro = g(42)
    assert inspect.iscoroutine(coro)
    assert time.time() - t0 < SLEEP_DELAY
    assert await coro == 1849
    assert time.time() - t0 > SLEEP_DELAY


class MyClass:
    async def start(self):
        self._q = asyncio.Queue()

    async def put(self, v):
        await self._q.put(v)

    async def get(self):
        return await self._q.get()

    async def __aenter__(self):
        await asyncio.sleep(SLEEP_DELAY)
        return 42

    async def __aexit__(self, exc_type, exc, tb):
        await asyncio.sleep(SLEEP_DELAY)


def test_class_sync():
    s = Synchronizer()
    NewClass = s(MyClass)
    obj = NewClass()
    obj.start()
    obj.put(42)
    fut = obj.get()
    assert isinstance(fut, concurrent.futures.Future)
    assert fut.result() == 42

    t0 = time.time()
    with obj as z:
        assert z == 42
        assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY

    assert time.time() - t0 > 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_class_async():
    s = Synchronizer()
    NewClass = s(MyClass)
    obj = NewClass()
    await obj.start()
    await obj.put(42)
    coro = obj.get()
    assert inspect.iscoroutine(coro)
    assert await coro == 42
