import pytest
import sys

from synchronicity import Synchronizer


async def f(x):
    return x ** 2


async def f_raises():
    raise Exception("boom!")


@pytest.mark.skipif(sys.version_info < (3, 7), reason="Python 3.7+")
def test_filter_tracebacks():
    s = Synchronizer(filter_tracebacks=True)
    f_s = s(f)
    assert f_s.__name__ == "f"
    ret = f_s(42)
    assert ret == 1764


@pytest.mark.skipif(sys.version_info < (3, 7), reason="Python 3.7+")
def test_filter_tracebacks_raises():
    s = Synchronizer(filter_tracebacks=True)
    f_raises_s = s(f_raises)
    assert f_raises_s.__name__ == "f_raises"
    with pytest.raises(Exception):
        f_raises_s()
