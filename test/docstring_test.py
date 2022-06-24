import asyncio
import pytest
from typing import Dict, Any

from synchronicity import Interface, Synchronizer


def test_docs():
    s = Synchronizer()

    class Foo:
        def __init__(self):
            """init docs"""
            self._attrs = {}

        def bar(self):
            """bar docs"""

    foo = Foo()
    assert foo.__init__.__doc__ == "init docs"
    assert foo.bar.__doc__ == "bar docs"

    BlockingFoo = s.create(Foo)[Interface.BLOCKING]
    blocking_foo = BlockingFoo()
    assert blocking_foo.__init__.__doc__ == "init docs"
    assert blocking_foo.bar.__doc__ == "bar docs"

    AsyncFoo = s.create(Foo)[Interface.ASYNC]
    async_foo = AsyncFoo()
    assert async_foo.__init__.__doc__ == "init docs"
    assert async_foo.bar.__doc__ == "bar docs"
