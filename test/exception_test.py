"""
Tests exceptions thrown from functions wrapped by Synchronicity.

Currently, exceptions are thrown from Synchronicity like so:

try:
    return self._func(*args, **kwargs)
except UserCodeException as uc_exc:
    uc_exc.exc.__suppress_context__ = True
    raise uc_exc.exc

When we raise an exception, the exception context is from Synchronicity, which
may confuse users. Therefore, we set __suppress_context__ to True to avoid
showing the user those error messages. This will preserve uc_exc.exc.__cause__,
but will cause uc_exc.exc.__context__ to be lost. Unfortunately, I don't know
how to avoid that.

These tests ensure that the __cause__ of an user exception is not lost, and
that either __suppress_context__ is True or __context__ is None so that users
are not exposed to confusing Synchronicity error messages.

See https://github.com/modal-labs/synchronicity/pull/165 for more details.
"""

import asyncio
import concurrent
import functools
import inspect
import pytest
import time
import typing

SLEEP_DELAY = 0.1


class CustomExceptionCause(Exception):
    pass


class CustomException(Exception):
    pass


async def f_raises():
    await asyncio.sleep(0.1)
    raise CustomException("something failed")


async def f_raises_with_cause():
    await asyncio.sleep(0.1)
    raise CustomException("something failed") from CustomExceptionCause("exception cause")


def test_function_raises_sync(synchronizer):
    t0 = time.monotonic()
    with pytest.raises(CustomException) as exc:
        f_raises_s = synchronizer.create_blocking(f_raises)
        f_raises_s()
    assert SLEEP_DELAY < time.monotonic() - t0 < 2 * SLEEP_DELAY
    assert exc.value.__suppress_context__ or exc.value.__context__ is None


def test_function_raises_with_cause_sync(synchronizer):
    t0 = time.monotonic()
    with pytest.raises(CustomException) as exc:
        f_raises_s = synchronizer.create_blocking(f_raises_with_cause)
        f_raises_s()
    assert SLEEP_DELAY < time.monotonic() - t0 < 2 * SLEEP_DELAY
    assert isinstance(exc.value.__cause__, CustomExceptionCause)


def test_function_raises_sync_futures(synchronizer):
    t0 = time.monotonic()
    f_raises_s = synchronizer.create_blocking(f_raises)
    fut = f_raises_s(_future=True)
    assert isinstance(fut, concurrent.futures.Future)
    assert time.monotonic() - t0 < SLEEP_DELAY
    with pytest.raises(CustomException) as exc:
        fut.result()
    assert SLEEP_DELAY < time.monotonic() - t0 < 2 * SLEEP_DELAY
    assert exc.value.__suppress_context__ or exc.value.__context__ is None


def test_function_raises_with_cause_sync_futures(synchronizer):
    t0 = time.monotonic()
    f_raises_s = synchronizer.create_blocking(f_raises_with_cause)
    fut = f_raises_s(_future=True)
    assert isinstance(fut, concurrent.futures.Future)
    assert time.monotonic() - t0 < SLEEP_DELAY
    with pytest.raises(CustomException) as exc:
        fut.result()
    assert SLEEP_DELAY < time.monotonic() - t0 < 2 * SLEEP_DELAY
    assert isinstance(exc.value.__cause__, CustomExceptionCause)


@pytest.mark.asyncio
async def test_function_raises_async(synchronizer):
    t0 = time.monotonic()
    f_raises_s = synchronizer.create_blocking(f_raises)
    coro = f_raises_s.aio()
    assert inspect.iscoroutine(coro)
    assert time.monotonic() - t0 < SLEEP_DELAY
    with pytest.raises(CustomException) as exc:
        await coro
    assert SLEEP_DELAY < time.monotonic() - t0 < 2 * SLEEP_DELAY
    assert exc.value.__suppress_context__ or exc.value.__context__ is None


@pytest.mark.asyncio
async def test_function_raises_with_cause_async(synchronizer):
    t0 = time.monotonic()
    f_raises_s = synchronizer.create_blocking(f_raises_with_cause)
    coro = f_raises_s.aio()
    assert inspect.iscoroutine(coro)
    assert time.monotonic() - t0 < SLEEP_DELAY
    with pytest.raises(CustomException) as exc:
        await coro
    assert SLEEP_DELAY < time.monotonic() - t0 < 2 * SLEEP_DELAY
    assert isinstance(exc.value.__cause__, CustomExceptionCause)


async def f_raises_baseexc():
    await asyncio.sleep(0.1)
    raise KeyboardInterrupt


def test_function_raises_baseexc_sync(synchronizer):
    t0 = time.monotonic()
    with pytest.raises(BaseException) as exc:
        f_raises_baseexc_s = synchronizer.create_blocking(f_raises_baseexc)
        f_raises_baseexc_s()
    assert SLEEP_DELAY < time.monotonic() - t0 < 2 * SLEEP_DELAY
    assert exc.value.__suppress_context__ or exc.value.__context__ is None


def f_raises_syncwrap() -> typing.Coroutine[typing.Any, typing.Any, None]:
    return f_raises()  # returns a coro


@pytest.mark.asyncio
async def test_function_raises_async_syncwrap(synchronizer):
    t0 = time.monotonic()
    f_raises_syncwrap_s = synchronizer.create_blocking(f_raises_syncwrap)
    coro = f_raises_syncwrap_s.aio()
    assert inspect.iscoroutine(coro)
    assert time.monotonic() - t0 < SLEEP_DELAY
    with pytest.raises(CustomException) as exc:
        await coro
    assert SLEEP_DELAY < time.monotonic() - t0 < 2 * SLEEP_DELAY
    assert exc.value.__suppress_context__ or exc.value.__context__ is None


def f_raises_with_cause_syncwrap() -> typing.Coroutine[typing.Any, typing.Any, None]:
    return f_raises_with_cause()  # returns a coro


@pytest.mark.asyncio
async def test_function_raises_with_cause_async_syncwrap(synchronizer):
    t0 = time.monotonic()
    f_raises_syncwrap_s = synchronizer.create_blocking(f_raises_with_cause_syncwrap)
    coro = f_raises_syncwrap_s.aio()
    assert inspect.iscoroutine(coro)
    assert time.monotonic() - t0 < SLEEP_DELAY
    with pytest.raises(CustomException) as exc:
        await coro
    assert SLEEP_DELAY < time.monotonic() - t0 < 2 * SLEEP_DELAY
    assert isinstance(exc.value.__cause__, CustomExceptionCause)


def decorator(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper


f_raises_wrapped = decorator(f_raises)


@pytest.mark.asyncio
async def test_wrapped_function_raises_async(synchronizer):
    t0 = time.monotonic()
    f_raises_s = synchronizer.create_blocking(f_raises_wrapped)
    coro = f_raises_s.aio()
    assert inspect.iscoroutine(coro)
    assert time.monotonic() - t0 < SLEEP_DELAY
    with pytest.raises(CustomException) as exc:
        await coro
    assert SLEEP_DELAY < time.monotonic() - t0 < 2 * SLEEP_DELAY
    assert exc.value.__suppress_context__ or exc.value.__context__ is None
