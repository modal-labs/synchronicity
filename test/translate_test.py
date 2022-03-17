import asyncio
import pytest

from synchronicity import Interface, Synchronizer


def test_translate():
    s = Synchronizer()

    class Foo:
        pass

    class FooProvider:
        def __init__(self):
            self.foo = Foo()

        def get(self):
            return self.foo

        def get2(self):
            return [self.foo, self.foo]

        def set(self, foo):
            assert type(foo) == Foo
            self.foo = foo

        @classmethod
        def cls_in(cls):
            assert cls == FooProvider

        @classmethod
        def cls_out(cls):
            return FooProvider

    names = {Interface.BLOCKING: "Foo_blocking"}
    Foo_blocking = s.create(Foo, names)[Interface.BLOCKING]
    names = {Interface.BLOCKING: "FooProvider_blocking"}
    FooProvider_blocking = s.create(FooProvider, names)[Interface.BLOCKING]
    foo_provider_blocking = FooProvider_blocking()

    # Make sure two instances translated out are the same
    foo1 = foo_provider_blocking.get()
    foo2 = foo_provider_blocking.get()
    assert foo1 == foo2

    # Make sure we can return a list
    foos = foo_provider_blocking.get2()
    return foos == [foo1, foo2]

    # Translate an object in and then back out, make sure it's the same
    foo = Foo_blocking()
    assert type(foo) != Foo
    foo_provider_blocking.set(foo)
    assert foo_provider_blocking.get() == foo

    # Make sure classes are translated properly too
    FooProvider_blocking.cls_in()
    assert FooProvider_blocking.cls_out() == FooProvider_blocking
