import asyncio
import pytest

from synchronicity import Synchronizer


async def noop():
    pass


async def error():
    raise Exception("problem")


class Resource:
    def __init__(self):
        self.state = "none"

    async def wrap(self):
        self.state = "entered"
        try:
            yield
        finally:
            self.state = "exited"

    async def wrap_yield_twice(self):
        yield
        yield

    async def wrap_never_yield(self):
        if False:
            yield


def test_asynccontextmanager_sync():
    r = Resource()
    s = Synchronizer()
    f = s.asynccontextmanager(r.wrap)
    assert r.state == "none"
    with f():
        assert r.state == "entered"
    assert r.state == "exited"


@pytest.mark.asyncio
async def test_asynccontextmanager_async():
    r = Resource()
    s = Synchronizer()
    f = s.asynccontextmanager(r.wrap)
    assert r.state == "none"
    async with f():
        assert r.state == "entered"
    assert r.state == "exited"


@pytest.mark.asyncio
async def test_asynccontextmanager_async_raise():
    r = Resource()
    s = Synchronizer()
    f = s.asynccontextmanager(r.wrap)
    assert r.state == "none"
    with pytest.raises(Exception):
        async with f():
            assert r.state == "entered"
            raise Exception("boom")
    assert r.state == "exited"


@pytest.mark.asyncio
async def test_asynccontextmanager_yield_twice():
    r = Resource()
    s = Synchronizer()
    f = s.asynccontextmanager(r.wrap_yield_twice)
    with pytest.raises(RuntimeError):
        async with f():
            pass


@pytest.mark.asyncio
async def test_asynccontextmanager_never_yield():
    r = Resource()
    s = Synchronizer()
    f = s.asynccontextmanager(r.wrap_never_yield)
    with pytest.raises(RuntimeError):
        async with f():
            pass
