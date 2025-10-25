import inspect

from synchronicity import Synchronizer


def f(x):
    return x**2


def test_multiwrap_warning(recwarn):
    s = Synchronizer(multiwrap_warning=True)
    try:
        f_s = s.create_blocking(f)
        assert f_s(42) == 1764
        assert len(recwarn) == 0
        f_s_s = s.create_blocking(f_s)
        assert f_s_s(42) == 1764
        assert len(recwarn) == 1
    finally:
        s._close_loop()  # clean up


def test_multiwrap_no_warning(recwarn, synchronizer):
    f_s = synchronizer.create_blocking(f)
    assert f_s(42) == 1764
    f_s_s = synchronizer.create_blocking(f_s)
    assert f_s_s(42) == 1764
    print("Recorded warnings 1:")
    for w in recwarn.list:
        print(str(w))
    assert len(recwarn) == 0


async def asyncgen():
    yield 42


async def returns_asyncgen():
    return asyncgen()


def test_check_double_wrapped(recwarn, synchronizer):
    assert len(recwarn) == 0
    ret = synchronizer.create_blocking(returns_asyncgen)()
    assert inspect.isasyncgen(ret)
    for w in recwarn.list:
        print("Recorded warning 2:", w)

    assert len(recwarn) == 1
