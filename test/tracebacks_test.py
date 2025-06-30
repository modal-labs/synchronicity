import contextlib
import pytest
import sys
import traceback
from pathlib import Path
from types import TracebackType


class CustomException(Exception):
    pass


async def raise_something(exc):
    raise exc


async def gen():
    raise CustomException("gen boom!")
    yield


def check_traceback(tb: TracebackType, outside_frames=0, outside_frames_old_python=1):
    traceback_string = "\n".join(traceback.format_tb(tb))
    assert str(Path(__file__)) in traceback_string  # this file should be in traceback
    n_outside = 0
    for frame in traceback.extract_tb(tb):
        if frame.filename != __file__:
            n_outside += 1

    # don't allow more than allowed_outside_frames from outside of this file
    limit = outside_frames_old_python if sys.version_info < (3, 11) else outside_frames
    if n_outside != limit:
        print(traceback_string)
        raise Exception(f"Got {n_outside} frames outside user code, expected {limit}")


def test_sync_to_async(synchronizer):
    raise_something_blocking = synchronizer.create_blocking(raise_something)
    with pytest.raises(CustomException) as exc_info:
        raise_something_blocking(CustomException("boom!"))

    check_traceback(exc_info.tb)
    traceback_string = "\n".join(traceback.format_tb(exc_info.tb))
    assert 'raise_something_blocking(CustomException("boom!"))' in traceback_string
    assert "raise exc" in traceback_string


def test_full_traceback_flag(synchronizer, monkeypatch):
    monkeypatch.setattr("synchronicity.exceptions.SYNCHRONICITY_TRACEBACK", True)
    raise_something_blocking = synchronizer.create_blocking(raise_something)
    with pytest.raises(CustomException) as exc_info:
        raise_something_blocking(CustomException("boom!"))

    check_traceback(exc_info.tb, outside_frames=8, outside_frames_old_python=8)
    traceback_string = "\n".join(traceback.format_tb(exc_info.tb))

    assert 'raise_something_blocking(CustomException("boom!"))' in traceback_string
    assert "raise exc" in traceback_string


@pytest.mark.asyncio
async def test_async_to_async(synchronizer):
    raise_something_wrapped = synchronizer.create_blocking(raise_something)
    with pytest.raises(CustomException) as exc_info:
        await raise_something_wrapped.aio(CustomException("boom!"))

    check_traceback(exc_info.tb)


def test_sync_to_async_gen(synchronizer):
    gen_s = synchronizer.create_blocking(gen)
    with pytest.raises(CustomException) as exc_info:
        for x in gen_s():
            pass

    check_traceback(exc_info.tb)


@pytest.mark.asyncio
async def test_async_to_async_gen(synchronizer):
    gen_s = synchronizer.create_blocking(gen)
    with pytest.raises(CustomException) as exc_info:
        async for x in gen_s.aio():
            pass

    check_traceback(exc_info.tb)


def test_sync_to_async_ctx_mgr(synchronizer):
    ctx_mgr = synchronizer.create_blocking(contextlib.asynccontextmanager(gen))
    with pytest.raises(CustomException) as exc_info:
        with ctx_mgr():
            pass

    # we allow one frame from contextlib which would be expected in non-synchronicity code
    # in old pythons we have to live with more synchronicity frames here due to multi
    # wrapping
    check_traceback(exc_info.tb, outside_frames=1, outside_frames_old_python=3)


@pytest.mark.asyncio
async def test_async_to_async_ctx_mgr(synchronizer):
    ctx_mgr = synchronizer.create_blocking(contextlib.asynccontextmanager(gen))
    with pytest.raises(CustomException) as exc_info:
        async with ctx_mgr():
            pass

    # we allow one frame from contextlib which would be expected in non-synchronicity code
    # in old pythons we have to live with more synchronicity frames here due to multi
    # wrapping
    check_traceback(exc_info.tb, outside_frames=1, outside_frames_old_python=3)


def test_recursive(synchronizer):
    async def f(n):
        if n == 0:
            raise CustomException("boom!")
        else:
            return await f(n - 1)

    f_blocking = synchronizer.create_blocking(f)

    with pytest.raises(CustomException) as exc_info:
        f_blocking(10)

    check_traceback(exc_info.tb)
