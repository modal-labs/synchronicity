def test_function_sync(synchronizer):
    async def f(x):
        return x**2

    f_blocking = synchronizer.create_blocking(f)
    assert f_blocking(42) == 1764
