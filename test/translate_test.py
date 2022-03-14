import asyncio
import pytest

from synchronicity import Synchronizer


def test_translate():
    s = Synchronizer()

    @s.mark
    class Foo:
        pass

    @s.mark
    class FooProvider:
        def __init__(self):
            self.foo = Foo()

        def get(self):
            return self.foo

    FooProvider_blocking = s.get_blocking(FooProvider)
    foo_provider_blocking = FooProvider_blocking()
    foo1 = foo_provider_blocking.get()
    foo2 = foo_provider_blocking.get()
    assert foo1 == foo2
