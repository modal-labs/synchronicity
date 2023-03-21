from synchronicity import Synchronizer


def test_function_sync():
    s = Synchronizer()

    async def f(x):
        return x**2

    f_blocking = s.create_blocking(f)
    assert f_blocking(42) == 1764
