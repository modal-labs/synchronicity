from synchronicity import Synchronizer, Interface


def test_function_sync():
    s = Synchronizer()

    async def f(x):
        return x**2

    f_blocking = s.create(f)[Interface.BLOCKING]
    assert f_blocking(42) == 1764
