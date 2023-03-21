import asyncio
import pytest

from synchronicity import Synchronizer

events = []


async def async_producer():
    for i in range(10):
        events.append("producer")
        yield i


@pytest.mark.asyncio
async def test_generator_order_async():
    events.clear()
    async_producer_synchronized = Synchronizer().create_async(async_producer)
    async for i in async_producer_synchronized():
        events.append("consumer")
    assert events == ["producer", "consumer"] * 10


@pytest.mark.asyncio
async def test_generator_order_explicit_async():
    events.clear()
    async_producer_synchronized = Synchronizer().create_async(async_producer)
    async for i in async_producer_synchronized():
        events.append("consumer")
    assert events == ["producer", "consumer"] * 10


def test_generator_order_sync():
    events.clear()
    async_producer_synchronized = Synchronizer().create_blocking(async_producer)
    for i in async_producer_synchronized():
        events.append("consumer")
    assert events == ["producer", "consumer"] * 10


async def async_bidirectional_producer(i):
    j = yield i
    assert j == i**2


@pytest.mark.asyncio
async def test_bidirectional_generator_async():
    f = Synchronizer().create_async(async_bidirectional_producer)
    gen = f(42)
    value = await gen.asend(None)
    assert value == 42
    with pytest.raises(StopAsyncIteration):
        await gen.asend(42 * 42)


def test_bidirectional_generator_sync():
    f = Synchronizer().create_blocking(async_bidirectional_producer)
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
async def test_athrow_async():
    gen = Synchronizer().create_async(athrow_example_gen)()
    v = await gen.asend(None)
    assert v == "hello"
    v = await gen.athrow(ZeroDivisionError)
    assert v == "world"


def test_athrow_sync():
    gen = Synchronizer().create_blocking(athrow_example_gen)()
    v = gen.send(None)
    assert v == "hello"
    v = gen.throw(ZeroDivisionError)
    assert v == "world"


@pytest.mark.asyncio
async def test_athrow_baseexc_async():
    gen = Synchronizer().create_async(athrow_example_gen)()
    v = await gen.asend(None)
    assert v == "hello"
    v = await gen.athrow(KeyboardInterrupt)
    assert v == "foobar"


def test_athrow_baseexc_sync():
    gen = Synchronizer().create_blocking(athrow_example_gen)()
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


def test_ensure_stop_async_iteration():
    events.clear()

    def create_generator():
        gen_f = Synchronizer().create_blocking(ensure_stop_async_iteration)
        for x in gen_f():
            break

    create_generator()
    assert len(events) == 1
    assert isinstance(events[0], GeneratorExit)


class MyGenerator:
    def __aiter__(self):
        return async_producer()


def test_custom_generator():
    events.clear()
    s = Synchronizer()
    BlockingMyGenerator = s.create_blocking(MyGenerator)
    blocking_my_generator = BlockingMyGenerator()
    for x in blocking_my_generator:
        events.append("consumer")
    assert events == ["producer", "consumer"] * 10
