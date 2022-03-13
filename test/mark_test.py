from synchronicity import Synchronizer, Interface


def test_function_sync():
    s = Synchronizer()

    @s.mark
    async def f(x):
        return x**2

    f_blocking = s.get(f, Interface.BLOCKING)
    assert f_blocking(42) == 1764
