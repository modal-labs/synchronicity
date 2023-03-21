from synchronicity import Synchronizer


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

    BlockingFoo = s.create_blocking(Foo)
    blocking_foo = BlockingFoo()
    assert blocking_foo.__init__.__doc__ == "init docs"
    assert blocking_foo.bar.__doc__ == "bar docs"

    AsyncFoo = s.create_async(Foo)
    async_foo = AsyncFoo()
    assert async_foo.__init__.__doc__ == "init docs"
    assert async_foo.bar.__doc__ == "bar docs"
