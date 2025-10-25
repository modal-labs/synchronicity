def test_docs(synchronizer):
    class Foo:
        def __init__(self):
            """init docs"""
            self._attrs = {}

        async def bar(self):
            """bar docs"""

    foo = Foo()
    assert foo.__init__.__doc__ == "init docs"
    assert foo.bar.__doc__ == "bar docs"

    BlockingFoo = synchronizer.create_blocking(Foo)
    blocking_foo = BlockingFoo()
    assert blocking_foo.__init__.__doc__ == "init docs"
    assert blocking_foo.bar.__doc__ == "bar docs"

    assert blocking_foo.bar.aio.__doc__ == "bar docs"
