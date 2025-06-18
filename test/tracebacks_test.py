import contextlib
import pytest
import sys
import traceback
from pathlib import Path
from types import TracebackType


class CustomException(Exception):
    pass


async def f():
    raise CustomException("boom!")


async def f_baseexc():
    raise KeyboardInterrupt


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
    f_s = synchronizer.create_blocking(f)
    try:
        f_s()
    except CustomException:
        check_traceback(sys.exc_info()[2])
        traceback_string = traceback.format_exc()
        assert "f_s()" in traceback_string
        assert 'raise CustomException("boom!")' in traceback_string
    else:
        assert False  # there should be an exception


def test_full_traceback_env_var(synchronizer, monkeypatch):
    monkeypatch.setenv("SYNCHRONICITY_TRACEBACK", "1")
    f_s = synchronizer.create_blocking(f)
    try:
        f_s()
    except CustomException:
        check_traceback(sys.exc_info()[2], outside_frames=8, outside_frames_old_python=8)
        traceback_string = traceback.format_exc()
        assert "f_s()" in traceback_string
        assert 'raise CustomException("boom!")' in traceback_string
    else:
        assert False  # there should be an exception


@pytest.mark.asyncio
async def test_async_to_async(synchronizer):
    f_s = synchronizer.create_blocking(f)
    try:
        await f_s.aio()
    except CustomException:
        check_traceback(sys.exc_info()[2])
    else:
        assert False


def test_sync_to_async_gen(synchronizer):
    gen_s = synchronizer.create_blocking(gen)
    try:
        for x in gen_s():
            pass
    except CustomException:
        check_traceback(sys.exc_info()[2])
    else:
        assert False


@pytest.mark.asyncio
async def test_async_to_async_gen(synchronizer):
    gen_s = synchronizer.create_blocking(gen)
    try:
        async for x in gen_s.aio():
            pass
    except CustomException:
        check_traceback(sys.exc_info()[2])
    else:
        raise


def test_sync_to_async_ctx_mgr(synchronizer):
    ctx_mgr = synchronizer.create_blocking(contextlib.asynccontextmanager(gen))
    try:
        with ctx_mgr():
            pass
    except CustomException:
        # we allow one frame from contextlib which would be expected in non-synchronicity code
        # in old pythons we have to live with more synchronicity frames here due to multi
        # wrapping
        check_traceback(sys.exc_info()[2], outside_frames=1, outside_frames_old_python=3)
    else:
        assert False


@pytest.mark.asyncio
async def test_async_to_async_ctx_mgr(synchronizer):
    ctx_mgr = synchronizer.create_blocking(contextlib.asynccontextmanager(gen))
    try:
        async with ctx_mgr():
            pass
    except CustomException:
        # we allow one frame from contextlib which would be expected in non-synchronicity code
        # in old pythons we have to live with more synchronicity frames here due to multi
        # wrapping
        check_traceback(sys.exc_info()[2], outside_frames=1, outside_frames_old_python=3)
    else:
        assert False


def test_recursive(synchronizer):
    async def f(n):
        if n == 0:
            raise CustomException("boom!")
        else:
            return await f(n - 1)

    f_blocking = synchronizer.create_blocking(f)

    try:
        f_blocking(10)
    except CustomException:
        check_traceback(sys.exc_info()[2])
    else:
        assert False
