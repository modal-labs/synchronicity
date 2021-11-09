import asyncio
import pytest

from synchronicity import Synchronizer


async def async_producer(events):
    for i in range(10):
        events.append("producer")
        yield i


@pytest.mark.asyncio
async def test_generator_order_async():
    events = []
    async_producer_synchronized = Synchronizer()(async_producer)
    async for i in async_producer_synchronized(events):
        events.append("consumer")
    assert events == ["producer", "consumer"] * 10


def test_generator_order_sync():
    events = []
    async_producer_synchronized = Synchronizer()(async_producer)
    for i in async_producer_synchronized(events):
        events.append("consumer")
    assert events == ["producer", "consumer"] * 10


async def async_bidirectional_producer(i):
    j = yield i
    assert j == i ** 2


@pytest.mark.asyncio
async def test_bidirectional_generator_async():
    f = Synchronizer()(async_bidirectional_producer)
    gen = f(42)
    value = await gen.asend(None)
    assert value == 42
    with pytest.raises(StopAsyncIteration):
        await gen.asend(42 * 42)


def test_bidirectional_generator_sync():
    f = Synchronizer()(async_bidirectional_producer)
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


@pytest.mark.asyncio
async def test_athrow_async():
    gen = Synchronizer()(athrow_example_gen)()
    v = await gen.asend(None)
    assert v == "hello"
    v = await gen.athrow(ZeroDivisionError)
    assert v == "world"


def test_athrow_sync():
    gen = Synchronizer()(athrow_example_gen)()
    v = gen.send(None)
    assert v == "hello"
    v = gen.throw(ZeroDivisionError)
    assert v == "world"
