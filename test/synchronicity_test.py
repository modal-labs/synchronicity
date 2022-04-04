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
    f_s = s(f)
    assert f_s.__name__ == "auto_f"
    ret = f_s(42)
    assert ret == 1764
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


def test_function_sync_future():
    s = Synchronizer()
    t0 = time.time()
    f_s = s(f)
    assert f_s.__name__ == "auto_f"
    fut = f_s(42, _future=True)
    assert isinstance(fut, concurrent.futures.Future)
    assert time.time() - t0 < SLEEP_DELAY
    assert fut.result() == 1764
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_function_async():
    s = Synchronizer()
    t0 = time.time()
    f_s = s(f)
    assert f_s.__name__ == "auto_f"
    coro = f_s(42)
    assert inspect.iscoroutine(coro)
    assert time.time() - t0 < SLEEP_DELAY
    assert await coro == 1764
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY

    # Make sure the same-loop calls work
    f2_s = s(f2)
    assert f2_s.__name__ == "auto_f2"
    coro = f2_s(f_s, 42)
    assert await coro == 1764

    # Make sure cross-loop calls work
    s2 = Synchronizer()
    f2_s2 = s2(f2)
    assert f2_s2.__name__ == "auto_f2"
    coro = f2_s2(f_s, 42)
    assert await coro == 1764


@pytest.mark.asyncio
async def test_function_async_block_event_loop():
    s = Synchronizer()

    async def spinlock():
        # This blocks the event loop, but not the main event loop
        time.sleep(SLEEP_DELAY)

    spinlock_s = s(spinlock)
    spinlock_coro = spinlock_s()
    sleep_coro = asyncio.sleep(SLEEP_DELAY)

    t0 = time.time()
    await asyncio.gather(spinlock_coro, sleep_coro)
    assert SLEEP_DELAY <= time.time() - t0 < 2 * SLEEP_DELAY


def test_function_many_parallel_sync():
    s = Synchronizer()
    g = s(f)
    t0 = time.time()
    rets = [g(i) for i in range(10)]  # Will resolve serially
    assert len(rets) * SLEEP_DELAY < time.time() - t0 < (len(rets) + 1) * SLEEP_DELAY


def test_function_many_parallel_sync_futures():
    s = Synchronizer()
    g = s(f)
    t0 = time.time()
    futs = [g(i, _future=True) for i in range(100)]
    assert isinstance(futs[0], concurrent.futures.Future)
    assert time.time() - t0 < SLEEP_DELAY
    assert [fut.result() for fut in futs] == [z**2 for z in range(100)]
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_function_many_parallel_async():
    s = Synchronizer()
    g = s(f)
    t0 = time.time()
    coros = [g(i) for i in range(100)]
    assert inspect.iscoroutine(coros[0])
    assert time.time() - t0 < SLEEP_DELAY
    assert await asyncio.gather(*coros) == [z**2 for z in range(100)]
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


class CustomException(Exception):
    pass


async def f_raises():
    await asyncio.sleep(0.1)
    raise CustomException("something failed")


def test_function_raises_sync():
    s = Synchronizer()
    t0 = time.time()
    with pytest.raises(CustomException):
        f_raises_s = s(f_raises)
        f_raises_s()
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY


def test_function_raises_sync_futures():
    s = Synchronizer()
    t0 = time.time()
    f_raises_s = s(f_raises)
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
    f_raises_s = s(f_raises)
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
        f_raises_baseexc_s = s(f_raises_baseexc)
        f_raises_baseexc_s()
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
    gen_s = s(gen)
    it = gen_s(3)
    assert inspect.isgenerator(it)
    assert time.time() - t0 < SLEEP_DELAY
    l = list(it)
    assert l == [0, 1, 2]
    assert time.time() - t0 > len(l) * SLEEP_DELAY


@pytest.mark.asyncio
async def test_generator_async():
    s = Synchronizer()
    t0 = time.time()
    gen_s = s(gen)
    asyncgen = gen_s(3)
    assert inspect.isasyncgen(asyncgen)
    assert time.time() - t0 < SLEEP_DELAY
    l = [z async for z in asyncgen]
    assert l == [0, 1, 2]
    assert time.time() - t0 > len(l) * SLEEP_DELAY

    # Make sure same-loop calls work
    gen2_s = s(gen2)
    asyncgen = gen2_s(gen_s, 3)
    l = [z async for z in asyncgen]
    assert l == [0, 1, 2]

    # Make sure cross-loop calls work
    s2 = Synchronizer()
    gen2_s2 = s2(gen2)
    asyncgen = gen2_s2(gen_s, 3)
    l = [z async for z in asyncgen]
    assert l == [0, 1, 2]


def test_sync_lambda_returning_coroutine_sync():
    s = Synchronizer()
    t0 = time.time()
    g = s(lambda z: f(z + 1))
    ret = g(42)
    assert ret == 1849
    assert time.time() - t0 > SLEEP_DELAY


def test_sync_lambda_returning_coroutine_sync_futures():
    s = Synchronizer()
    t0 = time.time()
    g = s(lambda z: f(z + 1))
    fut = g(42, _future=True)
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
    AutoMyClass = s(MyClass)
    AutoBase = s(Base)
    assert AutoMyClass.__name__ == "AutoMyClass"
    obj = AutoMyClass(x=42)
    assert isinstance(obj, AutoMyClass)
    assert isinstance(obj, AutoBase)
    obj.start()
    ret = obj.get_result()
    assert ret == 1764

    t0 = time.time()
    with obj as z:
        assert z == 42
        assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY
    assert time.time() - t0 > 2 * SLEEP_DELAY

    t0 = time.time()
    assert AutoMyClass.my_static_method() == 43
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY

    t0 = time.time()
    assert AutoMyClass.my_class_method() == 44
    assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY

    assert list(z for z in obj) == list(range(42))


def test_class_sync_futures():
    s = Synchronizer()
    AutoMyClass = s(MyClass)
    AutoBase = s(Base)
    assert AutoMyClass.__name__ == "AutoMyClass"
    obj = AutoMyClass(x=42)
    assert isinstance(obj, AutoMyClass)
    assert isinstance(obj, AutoBase)
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
    AutoMyClass = s(MyClass)
    AutoBase = s(Base)
    assert AutoMyClass.__name__ == "AutoMyClass"
    obj = AutoMyClass(x=42)
    assert isinstance(obj, AutoMyClass)
    assert isinstance(obj, AutoBase)
    await obj.start()
    coro = obj.get_result()
    assert inspect.iscoroutine(coro)
    assert await coro == 1764

    t0 = time.time()
    async with obj as z:
        assert z == 42
        assert SLEEP_DELAY < time.time() - t0 < 2 * SLEEP_DELAY

    assert time.time() - t0 > 2 * SLEEP_DELAY

    l = []
    async for z in obj:
        l.append(z)
    assert l == list(range(42))


@pytest.mark.asyncio
async def test_class_async_back_and_forth():
    s = Synchronizer()
    AutoMyClass = s(MyClass)
    AutoBase = s(Base)
    obj = AutoMyClass(x=42)
    assert isinstance(obj, AutoMyClass)
    assert isinstance(obj, AutoBase)
    await obj.start()

    def get(o):
        return o.get_result()  # Blocking

    loop = asyncio.get_event_loop()
    fut = loop.run_in_executor(None, get, obj)
    ret = await fut
    assert ret == 1764


# The problem here is that f is already synchronized by another synchronizer, which shouldn't be allowed
@pytest.mark.skip(
    reason="Skip this until we've made it impossible to re-synchronize objects"
)
def test_event_loop():
    s = Synchronizer()
    t0 = time.time()
    f_s = s(f)
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



@pytest.mark.parametrize("interface_type", [Interface.BLOCKING, Interface.ASYNC, Interface.AUTODETECT])
def test_doc_transfer(interface_type):
    class Foo:
        """Hello"""

        def foo(self):
            """hello"""

    s = Synchronizer()
    output_class = s.create(Foo)[interface_type]

    assert output_class.__doc__ == "Hello"
    assert output_class.foo.__doc__ == "hello"

