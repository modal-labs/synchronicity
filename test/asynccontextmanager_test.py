import pytest
import sys
from contextlib import asynccontextmanager


async def noop():
    pass


async def error():
    raise Exception("problem")


class Resource:
    def __init__(self):
        self.state = "none"

    def get_state(self):
        return self.state

    @asynccontextmanager
    async def wrap(self):
        self.state = "entered"
        try:
            yield
        finally:
            self.state = "exited"

    @asynccontextmanager
    async def wrap_yield_twice(self):
        yield
        yield

    @asynccontextmanager
    async def wrap_never_yield(self):
        if False:
            yield


def test_asynccontextmanager_sync(synchronizer):
    r = synchronizer.create_blocking(Resource)()
    assert r.get_state() == "none"
    with r.wrap():
        assert r.get_state() == "entered"
    assert r.get_state() == "exited"


@pytest.mark.asyncio
async def test_asynccontextmanager_async(synchronizer):
    r = synchronizer.create_async(Resource)()
    assert r.get_state() == "none"
    async with r.wrap():
        assert r.get_state() == "entered"
    assert r.get_state() == "exited"


@pytest.mark.asyncio
async def test_asynccontextmanager_async_raise(synchronizer):
    r = synchronizer.create_async(Resource)()
    assert r.get_state() == "none"
    with pytest.raises(Exception):
        async with r.wrap():
            assert r.get_state() == "entered"
            raise Exception("boom")
    assert r.get_state() == "exited"


@pytest.mark.asyncio
async def test_asynccontextmanager_yield_twice(synchronizer):
    r = synchronizer.create_async(Resource)()
    with pytest.raises(RuntimeError):
        async with r.wrap_yield_twice():
            pass


@pytest.mark.asyncio
async def test_asynccontextmanager_never_yield(synchronizer):
    r = synchronizer.create_async(Resource)()
    with pytest.raises(RuntimeError):
        async with r.wrap_never_yield():
            pass


@pytest.mark.asyncio
async def test_asynccontextmanager_nested(synchronizer):
    finally_blocks = []

    @synchronizer.create_async
    @asynccontextmanager
    async def a():
        try:
            yield "foo"
        finally:
            finally_blocks.append("A")

    @synchronizer.create_async
    @asynccontextmanager
    async def b():
        async with a() as it:
            try:
                yield it
            finally:
                finally_blocks.append("B")

    with pytest.raises(BaseException):
        async with b():
            raise BaseException("boom!")

    assert finally_blocks == ["B", "A"]


@pytest.mark.asyncio
async def test_asynccontextmanager_with_in_async(synchronizer):
    r = synchronizer.create_async(Resource)()
    err_cls = AttributeError if sys.version_info < (3, 11) else TypeError
    with pytest.raises(err_cls):
        with r.wrap():
            pass
