import pytest
import traceback

from synchronicity import Synchronizer


class CustomException(Exception):
    pass


async def f():
    raise CustomException("boom!")


async def f_baseexc():
    raise KeyboardInterrupt


async def gen():
    raise CustomException("gen boom!")
    yield


def check_traceback(exc):
    tb = exc.__traceback__
    n_outside = 0
    for frame in traceback.extract_tb(tb):
        if frame.filename != __file__:
            n_outside += 1

    # Let's allow for at most 1 entry outside of this file
    if n_outside > 1:
        for frame in traceback.extract_tb(tb):
            print(frame.filename, frame.lineno, frame.line)
        raise Exception(f"Got {n_outside} frames outside user code, expected 1")


def test_sync_to_async():
    s = Synchronizer()
    f_s = s.create_blocking(f)
    with pytest.raises(CustomException) as excinfo:
        f_s()
    check_traceback(excinfo.value)


@pytest.mark.asyncio
async def test_async_to_async():
    s = Synchronizer()
    f_s = s.create_async(f)
    with pytest.raises(CustomException) as excinfo:
        await f_s()
    check_traceback(excinfo.value)


def test_sync_to_async_gen():
    s = Synchronizer()
    gen_s = s.create_blocking(gen)
    with pytest.raises(CustomException) as excinfo:
        for x in gen_s():
            pass
    check_traceback(excinfo.value)


@pytest.mark.asyncio
async def test_async_to_async_gen():
    s = Synchronizer()
    gen_s = s.create_async(gen)
    with pytest.raises(CustomException) as excinfo:
        async for x in gen_s():
            pass
    check_traceback(excinfo.value)


@pytest.mark.skip(reason="This one will be much easier to fix once AUTODETECT is gone")
def test_sync_to_async_ctx_mgr():
    s = Synchronizer()
    ctx_mgr = s.create_blocking(s.asynccontextmanager(gen))
    with pytest.raises(CustomException) as excinfo:
        with ctx_mgr():
            pass
    check_traceback(excinfo.value)


@pytest.mark.skip(reason="This one will be much easier to fix once AUTODETECT is gone")
@pytest.mark.asyncio
async def test_async_to_async_ctx_mgr():
    s = Synchronizer()
    ctx_mgr = s.create_async(s.asynccontextmanager(gen))
    with pytest.raises(CustomException) as excinfo:
        async with ctx_mgr():
            pass
    check_traceback(excinfo.value)


def test_recursive():
    s = Synchronizer()

    async def f(n):
        if n == 0:
            raise CustomException("boom!")
        else:
            return await f(n - 1)

    with pytest.raises(CustomException) as excinfo:
        f_blocking = s.create_blocking(f)
        f_blocking(10)
    check_traceback(excinfo.value)
