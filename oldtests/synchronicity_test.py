import asyncio
import concurrent.futures
import gc
import inspect
import logging
import pytest
import sys
import threading
import time
import typing
from typing import Coroutine
from unittest.mock import MagicMock

from synchronicity import Synchronizer

SLEEP_DELAY = 0.5
WINDOWS_TIME_RESOLUTION_FIX = 0.01 if sys.platform == "win32" else 0.0


async def f(x):
    await asyncio.sleep(SLEEP_DELAY)
    return x**2


async def f2(fn, x):
    return await fn(x)


def test_function_sync(synchronizer):
    s = synchronizer
    t0 = time.monotonic()
    f_s = s.create_blocking(f)
    assert f_s.__name__ == "blocking_f"
    ret = f_s(42)
    assert ret == 1764
    assert SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= time.monotonic() - t0 < 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_function_async(synchronizer):
    s = synchronizer
    f_s = s.wrap(f)
    t0 = time.monotonic()
    ret = await f_s.aio(42)
    assert ret == 1764
    assert SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= time.monotonic() - t0 < 2 * SLEEP_DELAY


def test_function_sync_future(synchronizer):
    t0 = time.monotonic()
    f_s = synchronizer.create_blocking(f)
    assert f_s.__name__ == "blocking_f"
    fut = f_s(42, _future=True)
    assert isinstance(fut, concurrent.futures.Future)
    assert time.monotonic() - t0 < SLEEP_DELAY
    assert fut.result() == 1764
    assert SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= time.monotonic() - t0 < 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_function_async_as_function_attribute(synchronizer):
    s = synchronizer
    t0 = time.monotonic()
    f_s = s.create_blocking(f).aio
    assert f_s.__name__ == "aio_f"
    coro = f_s(42)
    assert inspect.iscoroutine(coro)
    assert time.monotonic() - t0 < SLEEP_DELAY
    assert await coro == 1764
    assert SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= time.monotonic() - t0 < 2 * SLEEP_DELAY

    # Make sure the same-loop calls work
    f2_s = s.create_blocking(f2).aio
    assert f2_s.__name__ == "aio_f2"
    coro = f2_s(f_s, 42)
    assert await coro == 1764

    # Make sure cross-loop calls work
    s2 = Synchronizer()
    f2_s2 = s2.create_blocking(f2).aio
    assert f2_s2.__name__ == "aio_f2"
    coro = f2_s2(f_s, 42)
    assert await coro == 1764
    s2._close_loop()


@pytest.mark.asyncio
async def test_function_async_block_event_loop(synchronizer):
    async def spinlock():
        # This blocks the event loop, but not the main event loop
        time.sleep(SLEEP_DELAY)

    spinlock_s = synchronizer.create_blocking(spinlock)
    spinlock_coro = spinlock_s.aio()
    sleep_coro = asyncio.sleep(SLEEP_DELAY)

    t0 = time.monotonic()
    await asyncio.gather(spinlock_coro, sleep_coro)
    duration = time.monotonic() - t0
    assert SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= duration < 1.5 * SLEEP_DELAY


def test_function_many_parallel_sync(synchronizer):
    g = synchronizer.create_blocking(f)
    t0 = time.monotonic()
    rets = [g(i) for i in range(10)]  # Will resolve serially
    assert (
        len(rets) * SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= time.monotonic() - t0 < (len(rets) + 1) * SLEEP_DELAY
    )


def test_function_many_parallel_sync_futures(synchronizer):
    g = synchronizer.create_blocking(f)
    t0 = time.monotonic()
    futs = [g(i, _future=True) for i in range(100)]
    assert isinstance(futs[0], concurrent.futures.Future)
    assert time.monotonic() - t0 < SLEEP_DELAY
    assert [fut.result() for fut in futs] == [z**2 for z in range(100)]
    assert SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= time.monotonic() - t0 < 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_function_many_parallel_async(synchronizer):
    g = synchronizer.create_blocking(f)
    t0 = time.monotonic()
    coros = [g.aio(i) for i in range(20)]
    assert inspect.iscoroutine(coros[0])
    assert time.monotonic() - t0 < 0.01  # invoking coroutine functions should be cheap
    assert await asyncio.gather(*coros) == [z**2 for z in range(20)]
    dur = time.monotonic() - t0
    assert SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= dur < 2 * SLEEP_DELAY


async def gen(n):
    for i in range(n):
        await asyncio.sleep(SLEEP_DELAY)
        yield i


async def gen2(generator, n):
    async for ret in generator(n):
        yield ret


def test_generator_sync(synchronizer):
    synchronizer = synchronizer
    t0 = time.monotonic()
    gen_s = synchronizer.create_blocking(gen)
    it = gen_s(3)
    assert inspect.isgenerator(it)
    assert time.monotonic() - t0 < SLEEP_DELAY
    lst = list(it)
    assert lst == [0, 1, 2]
    assert time.monotonic() - t0 + WINDOWS_TIME_RESOLUTION_FIX >= len(lst) * SLEEP_DELAY


@pytest.mark.asyncio
async def test_generator_async(synchronizer):
    t0 = time.monotonic()
    gen_s = synchronizer.create_blocking(gen).aio

    asyncgen = gen_s(3)
    assert inspect.isasyncgen(asyncgen)
    assert time.monotonic() - t0 < SLEEP_DELAY
    lst = [z async for z in asyncgen]
    assert lst == [0, 1, 2]
    assert time.monotonic() - t0 + WINDOWS_TIME_RESOLUTION_FIX >= len(lst) * SLEEP_DELAY

    # Make sure same-loop calls work
    gen2_s = synchronizer.create_blocking(gen2).aio
    asyncgen = gen2_s(gen_s, 3)
    lst = [z async for z in asyncgen]
    assert lst == [0, 1, 2]

    # Make sure cross-loop calls work
    s2 = synchronizer
    gen2_s2 = s2.create_blocking(gen2).aio
    asyncgen = gen2_s2(gen_s, 3)
    lst = [z async for z in asyncgen]
    assert lst == [0, 1, 2]


@pytest.mark.asyncio
async def test_function_returning_coroutine(synchronizer):
    def func() -> Coroutine:
        async def inner():
            return 10

        return inner()

    blocking_func = synchronizer.create_blocking(func)
    assert blocking_func() == 10
    coro = blocking_func.aio()
    assert inspect.iscoroutine(coro)
    assert await coro == 10


def test_sync_lambda_returning_coroutine_sync(synchronizer):
    t0 = time.monotonic()
    g = synchronizer.create_blocking(lambda z: f(z + 1))
    ret = g(42)
    assert ret == 1849
    assert time.monotonic() - t0 >= SLEEP_DELAY


def test_sync_lambda_returning_coroutine_sync_futures(synchronizer):
    t0 = time.monotonic()
    g = synchronizer.create_blocking(lambda z: f(z + 1))
    fut = g(42, _future=True)
    assert isinstance(fut, concurrent.futures.Future)
    assert time.monotonic() - t0 < SLEEP_DELAY
    assert fut.result() == 1849
    assert time.monotonic() - t0 >= SLEEP_DELAY


@pytest.mark.asyncio
async def test_sync_inline_func_returning_coroutine_async(synchronizer):
    t0 = time.monotonic()

    # NOTE: we don't create the async variant unless we know the function returns a coroutine
    def func(z) -> Coroutine:
        return f(z + 1)

    g = synchronizer.create_blocking(func)
    coro = g.aio(42)
    assert inspect.iscoroutine(coro)
    assert time.monotonic() - t0 < SLEEP_DELAY
    assert await coro == 1849
    assert time.monotonic() - t0 >= SLEEP_DELAY


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


def test_class_sync(synchronizer):
    BlockingBase = synchronizer.create_blocking(Base, name="BlockingBase")
    BlockingMyClass = synchronizer.create_blocking(MyClass, name="BlockingMyClass")

    assert BlockingMyClass.__name__ == "BlockingMyClass"
    obj = BlockingMyClass(x=42)
    assert isinstance(obj, BlockingMyClass)
    assert isinstance(obj, BlockingBase)
    obj.start()
    ret = obj.get_result()
    assert ret == 1764

    t0 = time.monotonic()
    with obj as z:
        assert z == 42
        assert SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= time.monotonic() - t0 < 2 * SLEEP_DELAY
    assert time.monotonic() - t0 + WINDOWS_TIME_RESOLUTION_FIX >= 2 * SLEEP_DELAY

    t0 = time.monotonic()
    assert BlockingMyClass.my_static_method() == 43
    assert SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= time.monotonic() - t0 < 2 * SLEEP_DELAY

    t0 = time.monotonic()
    assert BlockingMyClass.my_class_method() == 44
    assert SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= time.monotonic() - t0 < 2 * SLEEP_DELAY

    assert list(z for z in obj) == list(range(42))


def test_class_sync_futures(synchronizer):
    BlockingMyClass = synchronizer.create_blocking(MyClass)
    BlockingBase = synchronizer.create_blocking(Base)
    assert BlockingMyClass.__name__ == "BlockingMyClass"
    obj = BlockingMyClass(x=42)
    assert isinstance(obj, BlockingMyClass)
    assert isinstance(obj, BlockingBase)
    obj.start()
    fut = obj.get_result(_future=True)
    assert isinstance(fut, concurrent.futures.Future)
    assert fut.result() == 1764

    t0 = time.monotonic()
    with obj as z:
        assert z == 42
        assert SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= time.monotonic() - t0 < 2 * SLEEP_DELAY

    assert time.monotonic() - t0 + WINDOWS_TIME_RESOLUTION_FIX >= 2 * SLEEP_DELAY


@pytest.mark.asyncio
async def test_class_async_as_method_attribute(synchronizer):
    BlockingMyClass = synchronizer.create_blocking(MyClass)
    BlockingBase = synchronizer.create_blocking(Base)
    assert BlockingMyClass.__name__ == "BlockingMyClass"
    obj = BlockingMyClass(x=42)
    assert isinstance(obj, BlockingMyClass)
    assert isinstance(obj, BlockingBase)
    await obj.start.aio()
    coro = obj.get_result.aio()
    assert inspect.iscoroutine(coro)
    assert await coro == 1764

    t0 = time.monotonic()
    async with obj as z:
        assert z == 42
        assert SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= time.monotonic() - t0 < 2 * SLEEP_DELAY

    assert time.monotonic() - t0 + WINDOWS_TIME_RESOLUTION_FIX >= 2 * SLEEP_DELAY

    lst = []

    async for z in obj:
        lst.append(z)

    assert lst == list(range(42))

    assert await obj.my_static_method.aio() == 43
    assert await obj.my_class_method.aio() == 44


@pytest.mark.skip(reason="Skip this until we've made it impossible to re-synchronize objects")
def test_event_loop(synchronizer):
    t0 = time.monotonic()
    f_s = synchronizer.create_blocking(f)
    assert f_s(42) == 42 * 42
    assert SLEEP_DELAY - WINDOWS_TIME_RESOLUTION_FIX <= time.monotonic() - t0 < 2 * SLEEP_DELAY
    assert synchronizer._thread.is_alive()
    assert synchronizer._loop.is_running()
    synchronizer._close_loop()
    assert not synchronizer._loop.is_running()
    assert not synchronizer._thread.is_alive()

    new_loop = asyncio.new_event_loop()
    synchronizer._start_loop(new_loop)
    assert synchronizer._loop == new_loop
    assert synchronizer._loop.is_running()
    assert synchronizer._thread.is_alive()

    # Starting a loop again before closing throws.
    with pytest.raises(Exception):
        synchronizer._start_loop(new_loop)


def test_doc_transfer(synchronizer):
    class Foo:
        """Hello"""

        async def foo(self):
            """hello"""

    output_class = synchronizer.create_blocking(Foo)

    assert output_class.__doc__ == "Hello"
    assert output_class.foo.__doc__ == "hello"
    assert output_class.foo.aio.__doc__ == "hello"


def test_set_function_name(synchronizer):
    f_s = synchronizer.create_blocking(f, "xyz")
    assert f_s(42) == 1764
    assert f_s.__name__ == "xyz"


def test_set_class_name(synchronizer):
    BlockingBase = synchronizer.create_blocking(Base, "XYZBase")
    assert BlockingBase.__name__ == "XYZBase"
    BlockingMyClass = synchronizer.create_blocking(MyClass, "XYZMyClass")
    assert BlockingMyClass.__name__ == "XYZMyClass"


@pytest.mark.asyncio
async def test_blocking_nested_aio_returns_blocking_obj(synchronizer):
    class Foo:
        async def get_self(self):
            return self

    BlockingFoo = synchronizer.create_blocking(Foo)

    original = BlockingFoo()
    assert original.get_self() == original

    self_from_aio_interface = await original.get_self.aio()
    assert self_from_aio_interface == original
    assert isinstance(self_from_aio_interface, BlockingFoo)


def test_no_input_translation(monkeypatch, synchronizer):
    @synchronizer.create_blocking
    def does_input_translation(arg: float) -> str:
        return str(arg)

    @synchronizer.create_blocking
    @synchronizer.no_input_translation
    async def without_input_translation(arg: float) -> str:
        return str(arg)

    in_translate_spy = MagicMock(wraps=synchronizer._translate_scalar_in)
    monkeypatch.setattr(synchronizer, "_translate_scalar_in", in_translate_spy)
    does_input_translation(3.14)  # test without decorator, this *should* do input translation
    in_translate_spy.assert_called_once_with(3.14)

    in_translate_spy.reset_mock()
    without_input_translation(3.14)
    in_translate_spy.assert_not_called()


def test_no_output_translation(monkeypatch, synchronizer):
    @synchronizer.create_blocking
    def does_output_translation(arg: float) -> str:
        return str(arg)

    @synchronizer.create_blocking
    @synchronizer.no_output_translation
    async def without_output_translation(arg: float) -> str:
        return str(arg)

    out_translate_spy = MagicMock(wraps=synchronizer._translate_scalar_out)
    monkeypatch.setattr(synchronizer, "_translate_scalar_out", out_translate_spy)
    does_output_translation(3.14)  # test without decorator, this *should* do input translation
    out_translate_spy.assert_called_once_with("3.14")

    out_translate_spy.reset_mock()
    without_output_translation(3.14)
    out_translate_spy.assert_not_called()


@pytest.mark.asyncio
async def test_non_async_aiter(synchronizer):
    async def some_async_gen():
        yield "foo"
        yield "bar"

    class It:
        def __aiter__(self):
            self._gen = some_async_gen()
            return self

        async def __anext__(self):
            value = await self._gen.__anext__()
            return value

        async def aclose(self):
            await self._gen.aclose()

    WrappedIt = synchronizer.create_blocking(It, name="WrappedIt")

    # just a sanity check of the original iterable:
    orig_async_it = It()
    assert [v async for v in orig_async_it] == ["foo", "bar"]
    await orig_async_it.aclose()

    # check async iteration on the wrapped iterator
    it = WrappedIt()
    assert [v async for v in it] == ["foo", "bar"]
    await it.aclose()

    # check sync iteration on the wrapped iterator
    it = WrappedIt()
    assert list(it) == ["foo", "bar"]
    it.close()


def test_generic_baseclass(synchronizer):
    T = typing.TypeVar("T")
    V = typing.TypeVar("V")

    class GenericClass(typing.Generic[T, V]):
        async def do_something(self):
            return 1

    WrappedGenericClass = synchronizer.create_blocking(GenericClass, name="BlockingGenericClass")

    assert WrappedGenericClass[str, float].__args__ == (str, float)

    instance: WrappedGenericClass[str, float] = WrappedGenericClass()  #  should be allowed
    assert isinstance(instance, WrappedGenericClass)
    assert instance.do_something() == 1

    Q = typing.TypeVar("Q")
    Y = typing.TypeVar("Y")

    class GenericSubclass(GenericClass[Q, Y]):
        pass

    WrappedGenericSubclass = synchronizer.create_blocking(GenericSubclass, name="BlockingGenericSubclass")
    assert WrappedGenericSubclass[bool, int].__args__ == (bool, int)
    instance_2 = WrappedGenericSubclass()
    assert isinstance(instance_2, WrappedGenericSubclass)
    assert isinstance(instance_2, WrappedGenericClass)  # still instance of parent
    assert instance.do_something() == 1  # has base methods


@pytest.mark.asyncio
async def test_async_cancellation(synchronizer):
    states = []

    async def foo(abort_cancellation: bool, cancel_self: bool = False):
        states.append("ready")
        if cancel_self:
            asyncio.tasks.current_task().cancel()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            states.append("cancelled")
            await asyncio.sleep(0.1)
            states.append("handled cancellation")
            if not abort_cancellation:
                raise
        return "done"

    wrapped_foo = synchronizer.create_blocking(foo)

    async def start_task(abort_cancellation: bool, cancel_self: bool = False):
        states.clear()
        calling_task = asyncio.create_task(
            wrapped_foo.aio(abort_cancellation=abort_cancellation, cancel_self=cancel_self)
        )
        while "ready" not in states:
            await asyncio.sleep(0.01)  # don't cancel before the task even starts
        return calling_task

    # Case 1: cancel in parent goes into the coroutine and comes back out:
    calling_task = await start_task(abort_cancellation=False)
    calling_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await calling_task
    assert states == ["ready", "cancelled", "handled cancellation"]

    # Case 2: cancel in parent goes into the coroutine and is "aborted" by the coroutine:
    # Note: This is explicitly not allowed anymore, since we can't distinguish it from the task
    # finishing successfully before a cancellation takes place, and no cancellation
    # getting raised - causing unintended aborted cancellations in the calling event loop
    # calling_task = await start_task(abort_cancellation=True)
    # calling_task.cancel()
    # assert await calling_task == "done"
    # assert states == ["ready", "cancelled", "handled cancellation"]

    # Case 3: cancellation from within the coroutine itself comes back out:
    calling_task = await start_task(abort_cancellation=False, cancel_self=True)
    with pytest.raises(asyncio.CancelledError):
        await calling_task
    assert states == ["ready", "cancelled", "handled cancellation"]

    # Case 4: cancellation of the synchronicity task containing the coroutine itself
    # but it's caught and should not be propagated to the caller:
    calling_task = await start_task(abort_cancellation=True, cancel_self=True)
    assert await calling_task == "done"
    assert "ready" in states
    assert states == ["ready", "cancelled", "handled cancellation"]


@pytest.mark.asyncio
async def test_async_cancel_completes_successfully_still_cancels(synchronizer):
    # Reproduces a race where the synchronizer event loop finishes a task
    # before a cancellation has a chance to get scheduled, and as such
    # never bubbles up the cancellation, even though it was never
    # caught
    e = threading.Event()

    @synchronizer.wrap
    async def well_behaved_coro():
        e.wait()
        return 1

    local_task = asyncio.create_task(well_behaved_coro.aio())
    await asyncio.sleep(0.1)  # let other event loop block at e2.wait above
    # well_behaved_coro has not exited at this point, and local_task is not resolved
    assert not local_task.done()
    local_task.cancel()  # this schedules cancellation on other thread
    await asyncio.sleep(0.1)
    assert not local_task.cancelled()  # not yet fully cancelled!
    e.set()  # release other event loop at resolve point, simulating a race
    # users would typically assume that a cancellation of a non-done well behaved
    # task would race a cancellation error in the next await of that task:
    with pytest.raises(asyncio.CancelledError):
        await local_task


def test_async_inner_still_translates(synchronizer):
    class _V:
        pass

    V = synchronizer.wrap(_V)

    @synchronizer.wrap
    async def inner():
        return _V()

    @synchronizer.wrap
    async def outer():
        v = await inner.aio()
        assert isinstance(v, V)

    outer()


def test_blocking_in_async_callback():
    """Test that blocking_in_async_callback is called when sync wrapper is called from a foreign event loop."""
    called_funcs = []

    def callback(func):
        called_funcs.append(func)

    # Create synchronizer with callback
    s = Synchronizer(blocking_in_async_callback=callback)
    foreign_loop = None

    try:

        async def async_func():
            await asyncio.sleep(0.01)
            return 42

        sync_func = s.wrap(async_func)

        # Test 1: Call from within a foreign event loop - should trigger callback
        async def call_sync_from_async():
            # We're in an async context with a running loop - calling the sync function
            # should trigger the callback
            return sync_func()

        # Manually create and manage a foreign event loop
        foreign_loop = asyncio.new_event_loop()
        try:
            result = foreign_loop.run_until_complete(call_sync_from_async())
            assert result == 42
        finally:
            foreign_loop.close()
            foreign_loop = None

        # Verify the callback was called with the original function
        assert len(called_funcs) == 1
        assert called_funcs[0] == async_func

        # Test 2: Call from outside an event loop - should NOT trigger callback
        called_funcs.clear()
        result = sync_func()
        assert result == 42

        # Verify the callback was NOT called when called from outside an event loop
        assert len(called_funcs) == 0
    finally:
        if foreign_loop is not None and not foreign_loop.is_closed():
            foreign_loop.close()
        s._close_loop()


@pytest.mark.filterwarnings("ignore")
@pytest.mark.skipif(sys.version_info >= (3, 14), reason="Test flakes on 3.14")
def test_synchronizer_unexpected_thread_death(caplog):
    s = Synchronizer()

    @s.wrap
    async def dummy():
        return "works"

    class CustomError(Exception):
        pass

    caplog.set_level(logging.ERROR)
    assert dummy() == "works"
    assert len(caplog.records) == 0

    # terminate the thread
    def make_event_raise():
        # a bit ugly, but we use asyncio internals here to raise an "unexpected"
        # error inside of the inner thread by having the asyncio.Event.wait
        # seemingly raise an error (although that should never happen durin
        # actual operation)
        for waiter in s._stopping._waiters:
            if not waiter.done():
                waiter.set_exception(CustomError())

    s._loop.call_soon_threadsafe(make_event_raise)
    time.sleep(0.1)  # give the thread some time to die
    with pytest.raises(RuntimeError, match="Synchronizer thread unexpectedly died"):
        dummy()  # this should trigger an error

    (error_log,) = caplog.records
    assert "Traceback" in error_log.message
    assert "CustomError" in error_log.message
    s._close_loop()


def test_run_async_gen_runs_aclose(synchronizer):
    states = []

    @synchronizer.wrap
    async def genfunc(finalization_delay: float):
        states.append("init")
        try:
            for i in range(2):
                await asyncio.sleep(0.01)
                states.append(f"yield {i}")
                yield i
                states.append(f"send after {i}")
        except BaseException:
            states.append("start finalization")
            await asyncio.sleep(finalization_delay)
            states.append("done")

    # full iteration
    for _ in genfunc(0.01):
        pass

    assert states == [
        "init",
        "yield 0",
        "send after 0",
        "yield 1",
        "send after 1",
    ]

    states.clear()
    # partial iteration and then close due to gc etc:
    agen = iter(genfunc(0.01))
    next(agen)
    del agen  # this should close the wrapper generator, and propagate to the underlying asyncgen
    assert states == [
        "init",
        "yield 0",
        # never sends after first yield, but athrows
        "start finalization",
        "done",
    ]
    # timeout finalization
    states.clear()
    synchronizer._asyncgen_finalizer_timeout_seconds = 0.1
    agen = iter(genfunc(0.5))
    next(agen)
    del agen
    assert states == [
        "init",
        "yield 0",
        "start finalization",
        # no done! it should time out
    ]
    time.sleep(1)
    # runs finalization in the background if it times out
    assert states == ["init", "yield 0", "start finalization", "done"]


@pytest.mark.asyncio
async def test_run_async_gen_runs_aclose_async(synchronizer):
    states = []

    @synchronizer.wrap
    async def genfunc(finalization_delay: float):
        states.append("init")
        try:
            for i in range(2):
                await asyncio.sleep(0.01)
                states.append(f"yield {i}")
                yield i
                states.append(f"send after {i}")
        except BaseException:
            states.append("start finalization")
            await asyncio.sleep(finalization_delay)
            states.append("done")

    # full iteration
    async for _ in genfunc.aio(0.01):
        pass

    assert states == [
        "init",
        "yield 0",
        "send after 0",
        "yield 1",
        "send after 1",
    ]

    states.clear()
    # partial iteration and then close due to gc etc:
    agen = aiter(genfunc.aio(0.01))
    assert await anext(agen) == 0
    await agen.aclose()
    assert states == [
        "init",
        "yield 0",
        # never sends after first yield, but athrows
        "start finalization",
        "done",
    ]

    # timeout finalization
    states.clear()
    synchronizer._asyncgen_finalizer_timeout_seconds = 0.1
    agen = aiter(genfunc.aio(0.5))
    await anext(agen)
    await agen.aclose()
    assert states == [
        "init",
        "yield 0",
        "start finalization",
        # no done! it timed out
    ]

    await asyncio.sleep(1)
    # finalization logic still runs
    assert states == ["init", "yield 0", "start finalization", "done"]


def test_del_is_not_wrapped(synchronizer):
    events = []

    class A:
        def __init__(self):
            # mostly for sanity
            events.append(f"init {type(self).__name__}")

        def __del__(self):
            events.append(f"del {type(self).__name__}")

    WrappedA = synchronizer.wrap(A, name="WrappedA")
    a = WrappedA()

    del a
    gc.collect()  # this should collect both the wrapper and the wrapped instance
    assert events == [
        # we don't want to trigger the destructor of the implementation object
        # before it's actually getting deleted, otherwise we'll double delete
        # it, and what is worse - it may still get used post-__del__ from
        # some other context, so there should not be *two* "del A" here
        "init A",
        "del A",
    ]
