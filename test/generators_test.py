import asyncio
import concurrent.futures
import contextlib
import gc
import pytest

events = []


async def async_producer():
    for i in range(10):
        events.append("producer")
        yield i


@pytest.mark.asyncio
async def test_generator_order_async(synchronizer):
    events.clear()
    async_producer_synchronized = synchronizer.create_blocking(async_producer)
    async for i in async_producer_synchronized.aio():
        events.append("consumer")
    assert events == ["producer", "consumer"] * 10


@pytest.mark.asyncio
async def test_generator_order_explicit_async(synchronizer):
    events.clear()
    async_producer_synchronized = synchronizer.create_blocking(async_producer)
    async for i in async_producer_synchronized.aio():
        events.append("consumer")
    assert events == ["producer", "consumer"] * 10


def test_generator_order_sync(synchronizer):
    events.clear()
    async_producer_synchronized = synchronizer.create_blocking(async_producer)
    for i in async_producer_synchronized():
        events.append("consumer")
    assert events == ["producer", "consumer"] * 10


async def async_bidirectional_producer(i):
    j = yield i
    assert j == i**2


@pytest.mark.asyncio
async def test_bidirectional_generator_async(synchronizer):
    f = synchronizer.create_blocking(async_bidirectional_producer)
    gen = f.aio(42)
    value = await gen.asend(None)
    assert value == 42
    with pytest.raises(StopAsyncIteration):
        await gen.asend(42 * 42)


def test_bidirectional_generator_sync(synchronizer):
    f = synchronizer.create_blocking(async_bidirectional_producer)
    gen = f(42)
    value = gen.send(None)
    assert value == 42
    with pytest.raises(StopIteration):
        gen.send(42 * 42)


async def athrow_example_gen():
    try:
        await asyncio.sleep(0.1)
        yield "hello"
    except ZeroDivisionError:
        await asyncio.sleep(0.2)
        yield "world"
    except BaseException:
        yield "foobar"


@pytest.mark.asyncio
async def test_athrow_async(synchronizer):
    gen = synchronizer.create_blocking(athrow_example_gen).aio()
    v = await gen.asend(None)
    assert v == "hello"
    v = await gen.athrow(ZeroDivisionError)
    assert v == "world"
    await gen.aclose()


def test_athrow_sync(synchronizer):
    gen = synchronizer.create_blocking(athrow_example_gen)()
    v = gen.send(None)
    assert v == "hello"
    v = gen.throw(ZeroDivisionError)
    assert v == "world"


@pytest.mark.asyncio
async def test_athrow_baseexc_async(synchronizer):
    gen = synchronizer.create_blocking(athrow_example_gen).aio()
    v = await gen.asend(None)
    assert v == "hello"
    v = await gen.athrow(KeyboardInterrupt)
    assert v == "foobar"


def test_athrow_baseexc_sync(synchronizer):
    gen = synchronizer.create_blocking(athrow_example_gen)()
    v = gen.send(None)
    assert v == "hello"
    v = gen.throw(KeyboardInterrupt)
    assert v == "foobar"


async def ensure_stop_async_iteration():
    try:
        yield 42
        yield 43
    except BaseException as exc:
        events.append(exc)


def test_ensure_stop_async_iteration(synchronizer):
    events.clear()

    def create_generator():
        gen_f = synchronizer.create_blocking(ensure_stop_async_iteration)
        for x in gen_f():
            break

    create_generator()
    assert len(events) == 1
    assert isinstance(events[0], GeneratorExit)


class MyGenerator:
    def __aiter__(self):
        return async_producer()


def test_custom_generator(synchronizer):
    events.clear()
    BlockingMyGenerator = synchronizer.create_blocking(MyGenerator)
    blocking_my_generator = BlockingMyGenerator()
    for x in blocking_my_generator:
        events.append("consumer")
    assert events == ["producer", "consumer"] * 10


def _registered_asyncgens(loop, code):
    return [agen for agen in loop._asyncgens if agen.ag_code is code]


async def two_items():
    yield 1
    yield 2


@pytest.mark.asyncio
async def test_asyncgen_hooks_bound_to_synchronizer_loop_async(synchronizer):
    iterator = synchronizer.create_blocking(two_items).aio()
    assert await iterator.__anext__() == 1
    assert _registered_asyncgens(asyncio.get_running_loop(), two_items.__code__) == []
    assert len(_registered_asyncgens(synchronizer._get_loop(), two_items.__code__)) == 1
    await iterator.aclose()


def test_asyncgen_hooks_bound_to_synchronizer_loop_blocking(synchronizer):
    iterator = synchronizer.create_blocking(two_items)()
    assert next(iterator) == 1
    assert len(_registered_asyncgens(synchronizer._get_loop(), two_items.__code__)) == 1
    iterator.close()


async def keep_running_through_cancellation(seconds):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while (remaining := deadline - loop.time()) > 0:
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(remaining)


@pytest.mark.asyncio
async def test_abandoned_generator_finalized_on_synchronizer_loop(synchronizer):
    # A double cancellation makes the caller stop waiting for an in-flight asend and issue
    # aclose while the generator is still running. That aclose fails, leaving the generator
    # to be finalized by the GC - which must happen on the synchronizer loop.
    finalized_on_loop = concurrent.futures.Future()

    async def gen():
        try:
            yield 1
            await keep_running_through_cancellation(0.05)
            yield 2
        finally:
            finalized_on_loop.set_result(asyncio.get_running_loop())

    iterator = synchronizer.create_blocking(gen).aio()
    await iterator.__anext__()
    asend = asyncio.create_task(iterator.__anext__())
    await asyncio.sleep(0.01)
    asend.cancel()
    await asyncio.sleep(0.01)
    asend.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await asend
    del asend  # the cancelled task's traceback keeps a reference cycle to the generator alive

    await asyncio.sleep(0.1)  # let the in-flight asend finish on the synchronizer loop
    gc.collect()
    finalized_on = await asyncio.wait_for(asyncio.wrap_future(finalized_on_loop), timeout=1)
    assert finalized_on is synchronizer._get_loop()
