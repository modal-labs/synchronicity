def test_translate(synchronizer):
    class Foo:
        pass

    class FooProvider:
        def __init__(self, foo=None):
            if foo is not None:
                assert type(foo) is Foo
                self.foo = foo
            else:
                self.foo = Foo()

        def get(self):
            return self.foo

        def get2(self):
            return [self.foo, self.foo]

        @property
        def pget(self):
            return self.foo

        def set(self, foo):
            assert type(foo) is Foo
            self.foo = foo

        @classmethod
        def cls_in(cls):
            assert cls == FooProvider

        @classmethod
        def cls_out(cls):
            return FooProvider

    BlockingFoo = synchronizer.create_blocking(Foo)
    assert BlockingFoo.__name__ == "BlockingFoo"
    BlockingFooProvider = synchronizer.create_blocking(FooProvider)
    assert BlockingFooProvider.__name__ == "BlockingFooProvider"
    foo_provider = BlockingFooProvider()

    # Make sure two instances translated out are the same
    foo1 = foo_provider.get()
    foo2 = foo_provider.get()
    assert foo1 == foo2

    # Make sure we can return a list
    foos = foo_provider.get2()
    assert foos == [foo1, foo2]

    # Make sure properties work
    foo = foo_provider.pget
    assert isinstance(foo, BlockingFoo)

    # Translate an object in and then back out, make sure it's the same
    foo = BlockingFoo()
    assert type(foo) is BlockingFoo
    foo_provider.set(foo)
    assert foo_provider.get() == foo

    # Make sure classes are translated properly too
    BlockingFooProvider.cls_in()
    assert BlockingFooProvider.cls_out() == BlockingFooProvider

    # Make sure the constructor works
    foo = BlockingFoo()
    foo_provider = BlockingFooProvider(foo)
    assert foo_provider.get() == foo
