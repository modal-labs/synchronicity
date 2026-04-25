import asyncio
import pytest

from synchronicity2.synchronizer import Synchronizer


def test_resolve_wrapper_class_requires_wrapper_location():
    class Impl:
        pass

    sync = Synchronizer("test_synchronizer_missing_wrapper_location")

    with pytest.raises(RuntimeError, match="has no registered wrapper location"):
        sync._resolve_wrapper_class(Impl())


def test_run_function_sync_propagates_coroutine_timeout_error(monkeypatch):
    class DoneFuture:
        def __init__(self):
            self.calls = 0

        def result(self, timeout=None):
            self.calls += 1
            if self.calls > 5:
                raise AssertionError("swallowed coroutine TimeoutError in sync polling loop")
            raise TimeoutError("inner timeout")

        def done(self):
            return True

    sync = Synchronizer("test_synchronizer_timeout_sync")
    done_future = DoneFuture()

    monkeypatch.setattr(sync, "_is_inside_loop", lambda: False)
    monkeypatch.setattr(sync, "_get_loop", lambda start=False: object())
    monkeypatch.setattr(
        asyncio,
        "run_coroutine_threadsafe",
        lambda coro, loop: (coro.close(), done_future)[1],
    )

    with pytest.raises(TimeoutError, match="inner timeout"):
        sync._run_function_sync(object())


@pytest.mark.asyncio
async def test_run_function_async_propagates_coroutine_timeout_error(monkeypatch):
    sync = Synchronizer("test_synchronizer_timeout_async")

    done_future = object()
    wrapped_future = asyncio.get_running_loop().create_future()
    wrapped_future.set_exception(TimeoutError("inner timeout"))

    monkeypatch.setattr(sync, "_is_inside_loop", lambda: False)
    monkeypatch.setattr(sync, "_get_loop", lambda start=False: object())
    monkeypatch.setattr(
        asyncio,
        "run_coroutine_threadsafe",
        lambda coro, loop: (coro.close(), done_future)[1],
    )
    monkeypatch.setattr(asyncio, "wrap_future", lambda fut: wrapped_future)

    with pytest.raises(TimeoutError, match="inner timeout"):
        await asyncio.wait_for(sync._run_function_async(object()), timeout=0.5)
