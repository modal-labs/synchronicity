import asyncio
import pytest
from typing import Dict, Any

from synchronicity import Synchronizer


def test_getattr():
    s = Synchronizer()

    class Foo:
        _attrs: Dict[str, Any]

        def __init__(self):
            self._attrs = {}

        async def __getattr__(self, k):
            await asyncio.sleep(0.01)
            return self._attrs[k]

        def __setattr__(self, k, v):
            if k in self.__annotations__:
                # Only needed because the constructor sets _attrs
                self.__dict__[k] = v
            else:
                self._attrs[k] = v

        @property
        def z(self):
            return self._attrs["x"]

        @staticmethod
        def make_foo():
            return Foo()

    foo = Foo()
    foo.x = 42
    assert asyncio.run(foo.x) == 42
    with pytest.raises(KeyError):
        asyncio.run(foo.y)
    assert foo.z == 42

    BlockingFoo = s.create_blocking(Foo)

    blocking_foo = BlockingFoo()
    blocking_foo.x = 42
    assert blocking_foo.x == 42
    with pytest.raises(KeyError):
        blocking_foo.y
    assert blocking_foo.z == 42

    blocking_foo = BlockingFoo.make_foo()
    assert isinstance(blocking_foo, BlockingFoo)

    AsyncFoo = s.create_async(Foo)
    async_foo = AsyncFoo()
    async_foo.x = 42
    assert asyncio.run(async_foo.x) == 42
    assert async_foo.z == 42
