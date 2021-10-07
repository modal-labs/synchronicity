import asyncio
import pytest

from synchronicity import Synchronizer


async def async_producer(events):
    for i in range(10):
        events.append("producer")
        yield i


async def async_consumer(producer, events):
    async for i in producer:
        events.append("consumer")


def sync_consumer(producer, events):
    for i in producer:
        events.append("consumer")


@pytest.mark.asyncio
async def test_generator_order_async_async():
    events = []
    async_producer_synchronized = Synchronizer()(async_producer)
    await async_consumer(async_producer_synchronized(events), events)
    assert events == ["producer", "consumer"] * 10


def test_generator_order_async_sync():
    events = []
    async_producer_synchronized = Synchronizer()(async_producer)
    sync_consumer(async_producer_synchronized(events), events)
    assert events == ["producer", "consumer"] * 10
