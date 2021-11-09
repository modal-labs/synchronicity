import pytest

from synchronicity import Synchronizer


async def f(x):
    return x ** 2


async def f_raises():
    return Exception("boom!")


def test_filter_tracebacks():
    s = Synchronizer(filter_tracebacks=True)
    f_s = s(f)
    assert f_s.__name__ == "f"
    ret = f_s(42)
    assert ret == 1764


def test_filter_tracebacks_raises():
    s = Synchronizer(filter_tracebacks=True)
    f_raises_s = s(f_raises)
    assert f_raises_s.__name__ == "f_raises"
    with pytest.raises(Exception):
        ret = f_raises_s()
        print("ret =", ret)
