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

        def set(self, foo):
            self.foo = foo

    Foo_blocking = s.get_blocking(Foo)
    FooProvider_blocking = s.get_blocking(FooProvider)
    foo_provider_blocking = FooProvider_blocking()

    # Make sure two instances translated out are the same
    foo1 = foo_provider_blocking.get()
    foo2 = foo_provider_blocking.get()
    assert foo1 == foo2

    # Translate an object in and then back out, make sure it's the same
    foo = Foo_blocking()
    foo_provider_blocking.set(foo)
    assert foo_provider_blocking.get() == foo
