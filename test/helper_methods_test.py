from synchronicity import Synchronizer


def test_is_synchronized():
    s = Synchronizer()

    class Foo:
        pass

    BlockingFoo = s.create_blocking(Foo)
    assert s.is_synchronized(Foo) is False
    assert s.is_synchronized(BlockingFoo) is True
