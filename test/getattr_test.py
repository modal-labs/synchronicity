import asyncio
import pytest
from typing import Dict, Any

from synchronicity import Interface, Synchronizer


def test_getattr():
    s = Synchronizer()

    class Foo:
        _attrs: Dict[str, Any]

        def __init__(self):
            self._attrs = {}

        async def __getattr__(self, k):
            await asyncio.sleep(0.01)
            if k in self.__annotations__:
                return self.__dict__[k]
            else:
                return self._attrs[k]

        def __setattr__(self, k, v):
            if k in self.__annotations__:
                self.__dict__[k] = v
            else:
                self._attrs[k] = v

        @staticmethod
        def make_foo():
            return Foo()

    def run(coro):
        # Python 3.6 compat
        return asyncio.get_event_loop().run_until_complete(coro)

    foo = Foo()
    foo.x = 42
    assert run(foo.x) == 42
    with pytest.raises(KeyError):
        run(foo.y)

    BlockingFoo = s.create(Foo)[Interface.BLOCKING]

    blocking_foo = BlockingFoo()
    blocking_foo.x = 42
    assert blocking_foo.x == 42
    with pytest.raises(KeyError):
        blocking_foo.y

    blocking_foo = BlockingFoo.make_foo()
    assert isinstance(blocking_foo, BlockingFoo)

    AsyncFoo = s.create(Foo)[Interface.ASYNC]
    async_foo = AsyncFoo()
    async_foo.x = 42
    assert run(async_foo.x) == 42
