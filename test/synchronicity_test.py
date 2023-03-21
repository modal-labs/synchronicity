import asyncio
import concurrent.futures
import inspect
import pytest
import time

from synchronicity import Synchronizer, Interface

SLEEP_DELAY = 0.1


async def f(x):
    await asyncio.sleep(SLEEP_DELAY)
    return x**2


async def f2(fn, x):
    return await fn(x)


def test_function_sync():
    s = Synchronizer()
    t0 = time.time()
    f_s = s.create_blocking(f)
    assert f_s.__name__ == "blocking_f"
    ret = f_s(42)
    assert ret == 1764
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


def test_function_sync_future():
    s = Synchronizer()
    t0 = time.time()
    f_s = s.create_blocking(f)
    assert f_s.__name__ == "blocking_f"
    fut = f_s(42, _future=True)
    assert isinstance(fut, concurrent.futures.Future)
    assert time.time() - t0 < SLEEP_DELAY
    assert fut.result() == 1764
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_function_async():
    s = Synchronizer()
    t0 = time.time()
    f_s = s.create_async(f)
    assert f_s.__name__ == "async_f"
    coro = f_s(42)
    assert inspect.iscoroutine(coro)
    assert time.time() - t0 < SLEEP_DELAY
    assert await coro == 1764
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY

    # Make sure the same-loop calls work
    f2_s = s.create_async(f2)
    assert f2_s.__name__ == "async_f2"
    coro = f2_s(f_s, 42)
    assert await coro == 1764

    # Make sure cross-loop calls work
    s2 = Synchronizer()
    f2_s2 = s2.create_async(f2)
    assert f2_s2.__name__ == "async_f2"
    coro = f2_s2(f_s, 42)
    assert await coro == 1764


@pytest.mark.asyncio
async def test_function_async_block_event_loop():
    s = Synchronizer()

    async def spinlock():
        # This blocks the event loop, but not the main event loop
        time.sleep(SLEEP_DELAY)

    spinlock_s = s.create_async(spinlock)
    spinlock_coro = spinlock_s()
    sleep_coro = asyncio.sleep(SLEEP_DELAY)

    t0 = time.time()
    await asyncio.gather(spinlock_coro, sleep_coro)
    assert SLEEP_DELAY <= time.time() - t0 < 2 * SLEEP_DELAY


def test_function_many_parallel_sync():
    s = Synchronizer()
    g = s.create_blocking(f)
    t0 = time.time()
    rets = [g(i) for i in range(10)]  # Will resolve serially
    assert len(rets) * SLEEP_DELAY < time.time() - t0 < (len(rets) + 1) * SLEEP_DELAY


def test_function_many_parallel_sync_futures():
    s = Synchronizer()
    g = s.create_blocking(f)
    t0 = time.time()
    futs = [g(i, _future=True) for i in range(100)]
    assert isinstance(futs[0], concurrent.futures.Future)
    assert time.time() - t0 < SLEEP_DELAY
    assert [fut.result() for fut in futs] == [z**2 for z in range(100)]
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_function_many_parallel_async():
    s = Synchronizer()
    g = s.create_async(f)
    t0 = time.time()
    coros = [g(i) for i in range(100)]
    assert inspect.iscoroutine(coros[0])
    assert time.time() - t0 < SLEEP_DELAY
    assert await asyncio.gather(*coros) == [z**2 for z in range(100)]
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


async def gen(n):
    for i in range(n):
        await asyncio.sleep(0.1)
        yield i


async def gen2(generator, n):
    async for ret in generator(n):
        yield ret


def test_generator_sync():
    s = Synchronizer()
    t0 = time.time()
    gen_s = s.create_blocking(gen)
    it = gen_s(3)
    assert inspect.isgenerator(it)
    assert time.time() - t0 < SLEEP_DELAY
    lst = list(it)
    assert lst == [0, 1, 2]
    assert time.time() - t0 > len(lst) * SLEEP_DELAY


@pytest.mark.asyncio
async def test_generator_async():
    s = Synchronizer()
    t0 = time.time()
    gen_s = s.create_async(gen)
    asyncgen = gen_s(3)
    assert inspect.isasyncgen(asyncgen)
    assert time.time() - t0 < SLEEP_DELAY
    lst = [z async for z in asyncgen]
    assert lst == [0, 1, 2]
    assert time.time() - t0 > len(lst) * SLEEP_DELAY

    # Make sure same-loop calls work
    gen2_s = s.create_async(gen2)
    asyncgen = gen2_s(gen_s, 3)
    lst = [z async for z in asyncgen]
    assert lst == [0, 1, 2]

    # Make sure cross-loop calls work
    s2 = Synchronizer()
    gen2_s2 = s2.create_async(gen2)
    asyncgen = gen2_s2(gen_s, 3)
    lst = [z async for z in asyncgen]
    assert lst == [0, 1, 2]


def test_sync_lambda_returning_coroutine_sync():
    s = Synchronizer()
    t0 = time.time()
    g = s.create_blocking(lambda z: f(z + 1))
    ret = g(42)
    assert ret == 1849
    assert time.time() - t0 > SLEEP_DELAY


def test_sync_lambda_returning_coroutine_sync_futures():
    s = Synchronizer()
    t0 = time.time()
    g = s.create_blocking(lambda z: f(z + 1))
    fut = g(42, _future=True)
    assert isinstance(fut, concurrent.futures.Future)
    assert time.time() - t0 < SLEEP_DELAY
    assert fut.result() == 1849
    assert time.time() - t0 > SLEEP_DELAY


@pytest.mark.asyncio
async def test_sync_lambda_returning_coroutine_async():
    s = Synchronizer()
    t0 = time.time()
    g = s.create_async(lambda z: f(z + 1))
    coro = g(42)
    assert inspect.iscoroutine(coro)
    assert time.time() - t0 < SLEEP_DELAY
    assert await coro == 1849
    assert time.time() - t0 > SLEEP_DELAY


class Base:
    def __init__(self, x):
        self._x = x


class MyClass(Base):
    def __init__(self, x):
        super().__init__(x)

    async def start(self):
        async def task():
            await asyncio.sleep(SLEEP_DELAY)
            return self._x

        loop = asyncio.get_event_loop()
        self._task = loop.create_task(task())

    async def get_result(self):
        ret = await self._task
        return ret**2

    async def __aenter__(self):
        await asyncio.sleep(SLEEP_DELAY)
        return 42

    async def __aexit__(self, exc_type, exc, tb):
        await asyncio.sleep(SLEEP_DELAY)

    @staticmethod
    async def my_static_method():
        await asyncio.sleep(SLEEP_DELAY)
        return 43

    @classmethod
    async def my_class_method(cls):
        await asyncio.sleep(SLEEP_DELAY)
        return 44

    async def __aiter__(self):
        for i in range(self._x):
            yield i


def test_class_sync():
    s = Synchronizer()
    BlockingMyClass = s.create_blocking(MyClass)
    BlockingBase = s.create_blocking(Base)
    assert BlockingMyClass.__name__ == "BlockingMyClass"
    obj = BlockingMyClass(x=42)
    assert isinstance(obj, BlockingMyClass)
    assert isinstance(obj, BlockingBase)
    obj.start()
    ret = obj.get_result()
    assert ret == 1764

    t0 = time.time()
    with obj as z:
        assert z == 42
        assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY
    assert time.time() - t0 > 2 * SLEEP_DELAY

    t0 = time.time()
    assert BlockingMyClass.my_static_method() == 43
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY

    t0 = time.time()
    assert BlockingMyClass.my_class_method() == 44
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY

    assert list(z for z in obj) == list(range(42))


def test_class_sync_futures():
    s = Synchronizer()
    BlockingMyClass = s.create_blocking(MyClass)
    BlockingBase = s.create_blocking(Base)
    assert BlockingMyClass.__name__ == "BlockingMyClass"
    obj = BlockingMyClass(x=42)
    assert isinstance(obj, BlockingMyClass)
    assert isinstance(obj, BlockingBase)
    obj.start()
    fut = obj.get_result(_future=True)
    assert isinstance(fut, concurrent.futures.Future)
    assert fut.result() == 1764

    t0 = time.time()
    with obj as z:
        assert z == 42
        assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY

    assert time.time() - t0 > 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_class_async():
    s = Synchronizer()
    AsyncMyClass = s.create_async(MyClass)
    AsyncBase = s.create_async(Base)
    assert AsyncMyClass.__name__ == "AsyncMyClass"
    obj = AsyncMyClass(x=42)
    assert isinstance(obj, AsyncMyClass)
    assert isinstance(obj, AsyncBase)
    await obj.start()
    coro = obj.get_result()
    assert inspect.iscoroutine(coro)
    assert await coro == 1764

    t0 = time.time()
    async with obj as z:
        assert z == 42
        assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY

    assert time.time() - t0 > 2 * SLEEP_DELAY

    lst = []
    async for z in obj:
        lst.append(z)
    assert lst == list(range(42))


@pytest.mark.asyncio
async def test_class_async_back_and_forth():
    s = Synchronizer()
    AsyncMyClass = s.create_async(MyClass)
    AsyncBase = s.create_async(Base)
    s.create_blocking(MyClass)
    async_obj = AsyncMyClass(x=42)
    assert isinstance(async_obj, AsyncMyClass)
    assert isinstance(async_obj, AsyncBase)
    await async_obj.start()

    def get(o):
        return o.get_result()  # Blocking

    # Make it into a sync object
    blocking_obj = s._translate_out(s._translate_in(async_obj), Interface.BLOCKING)
    assert type(blocking_obj).__name__ == "BlockingMyClass"

    # Run it in a sync context
    loop = asyncio.get_event_loop()
    fut = loop.run_in_executor(None, get, blocking_obj)
    ret = await fut
    assert ret == 1764

    # The problem here is that f is already synchronized by another synchronizer, which shouldn't be allowed


@pytest.mark.skip(
    reason="Skip this until we've made it impossible to re-synchronize objects"
)
def test_event_loop():
    s = Synchronizer()
    t0 = time.time()
    f_s = s.create_blocking(f)
    assert f_s(42) == 42 * 42
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY
    assert s._thread.is_alive()
    assert s._loop.is_running()
    s._close_loop()
    assert not s._loop.is_running()
    assert not s._thread.is_alive()

    new_loop = asyncio.new_event_loop()
    s._start_loop(new_loop)
    assert s._loop == new_loop
    assert s._loop.is_running()
    assert s._thread.is_alive()

    # Starting a loop again before closing throws.
    with pytest.raises(Exception):
        s._start_loop(new_loop)


@pytest.mark.parametrize("interface_type", [Interface.BLOCKING, Interface.ASYNC])
def test_doc_transfer(interface_type):
    class Foo:
        """Hello"""

        def foo(self):
            """hello"""

    s = Synchronizer()
    output_class = s._wrap(Foo, interface_type)

    assert output_class.__doc__ == "Hello"
    assert output_class.foo.__doc__ == "hello"


def test_set_function_name():
    s = Synchronizer()
    f_s = s.create_blocking(f, "xyz")
    assert f_s(42) == 1764
    assert f_s.__name__ == "xyz"


def test_set_class_name():
    s = Synchronizer()
    BlockingBase = s.create_blocking(Base, "XYZBase")
    assert BlockingBase.__name__ == "XYZBase"
    BlockingMyClass = s.create_blocking(MyClass, "XYZMyClass")
    assert BlockingMyClass.__name__ == "XYZMyClass"
