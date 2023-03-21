import inspect

from synchronicity import Synchronizer


def f(x):
    return x**2


def test_multiwrap_warning(recwarn):
    s = Synchronizer(multiwrap_warning=True)
    f_s = s.create_blocking(f)
    assert f_s(42) == 1764
    assert len(recwarn) == 0
    f_s_s = s.create_blocking(f_s)
    assert f_s_s(42) == 1764
    assert len(recwarn) == 1


def test_multiwrap_no_warning(recwarn):
    s = Synchronizer()
    f_s = s.create_blocking(f)
    assert f_s(42) == 1764
    f_s_s = s.create_blocking(f_s)
    assert f_s_s(42) == 1764
    assert len(recwarn) == 0


async def asyncgen():
    yield 42


async def returns_asyncgen():
    return asyncgen()


def test_check_double_wrapped(recwarn):
    s = Synchronizer()
    assert len(recwarn) == 0
    ret = s.create_blocking(returns_asyncgen)()
    assert inspect.isasyncgen(ret)
    assert len(recwarn) == 1
