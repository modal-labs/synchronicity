def test_is_synchronized(synchronizer):
    class Foo:
        pass

    BlockingFoo = synchronizer.create_blocking(Foo)
    assert synchronizer.is_synchronized(Foo) is False
    assert synchronizer.is_synchronized(BlockingFoo) is True
