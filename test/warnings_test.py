import warnings

from synchronicity import Synchronizer


def f(x):
    return x ** 2


def test_multiwrap_warning(recwarn):
    s = Synchronizer(multiwrap_warning=True)
    f_s = s(f)
    assert f_s(42) == 1764
    assert len(recwarn) == 0
    f_s_s = s(f_s)
    assert f_s_s(42) == 1764
    assert len(recwarn) == 1


def test_multiwrap_no_warning(recwarn):
    s = Synchronizer()
    f_s = s(f)
    assert f_s(42) == 1764
    f_s_s = s(f_s)
    assert f_s_s(42) == 1764
    assert len(recwarn) == 0
