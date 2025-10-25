import asyncio
import atexit
import concurrent.futures
import os
import threading
import typing
from typing import Optional

# Global registry for synchronizer instances
_synchronizer_registry = {}


def get_synchronizer(name: str) -> "Synchronizer":
    """Get or create a synchronizer instance by name from the global registry."""
    if name not in _synchronizer_registry:
        _synchronizer_registry[name] = Synchronizer(name)
    return _synchronizer_registry[name]


class Synchronizer:
    def __init__(self, name: Optional[str] = None):
        self._name = name
        self._future_poll_interval = 0.1
        self._loop = None
        self._loop_creation_lock = threading.Lock()
        self._thread = None
        self._owner_pid = None
        self._stopping = None

        # Special attribute we use to go from wrapped <-> original
        self._wrapped_attr = "_sync_wrapped_%d" % id(self)
        self._original_attr = "_sync_original_%d" % id(self)

        # Special attribute to mark something as non-wrappable
        self._nowrap_attr = "_sync_nonwrap_%d" % id(self)
        self._input_translation_attr = "_sync_input_translation_%d" % id(self)
        self._output_translation_attr = "_sync_output_translation_%d" % id(self)

        atexit.register(self._close_loop)

    _PICKLE_ATTRS = [
        "_multiwrap_warning",
        "_async_leakage_warning",
    ]

    def __getstate__(self):
        return dict([(attr, getattr(self, attr)) for attr in self._PICKLE_ATTRS])

    def __setstate__(self, d):
        for attr in self._PICKLE_ATTRS:
            setattr(self, attr, d[attr])

    def _start_loop(self):
        with self._loop_creation_lock:
            if self._loop and self._loop.is_running():
                # in case of a race between two _start_loop, the loop might already
                # be created here by another thread
                return self._loop

            is_ready = threading.Event()

            def thread_inner():
                async def loop_inner():
                    self._loop = asyncio.get_running_loop()
                    self._stopping = asyncio.Event()
                    is_ready.set()
                    await self._stopping.wait()  # wait until told to stop

                try:
                    asyncio.run(loop_inner())
                except RuntimeError as exc:
                    # Python 3.12 raises a RuntimeError when new threads are created at shutdown.
                    # Swallowing it here is innocuous, but ideally we will revisit this after
                    # refactoring the shutdown handlers that modal uses to avoid triggering it.
                    if "can't create new thread at interpreter shutdown" not in str(exc):
                        raise exc

            self._owner_pid = os.getpid()
            thread = threading.Thread(target=thread_inner, daemon=True)
            thread.start()
            is_ready.wait()  # TODO: this might block for a very short time
            self._thread = thread
            return self._loop

    def _close_loop(self):
        # Use getattr to protect against weird gc races when we get here via __del__
        if getattr(self, "_thread", None) is not None:
            if not self._loop.is_closed():
                # This also serves the purpose of waking up an idle loop
                self._loop.call_soon_threadsafe(self._stopping.set)
            self._thread.join()
            self._thread = None
            self._loop = None
            self._owner_pid = None

    def _get_loop(self, start=False) -> asyncio.AbstractEventLoop:
        if self._thread and not self._thread.is_alive():
            if self._owner_pid == os.getpid():
                # warn - thread died without us forking
                raise RuntimeError("Synchronizer thread unexpectedly died")

            self._thread = None
            self._loop = None

        if self._loop is None and start:
            return self._start_loop()
        return self._loop

    def _get_running_loop(self):
        # TODO: delete this method
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return

    def _is_inside_loop(self):
        loop = self._get_loop()
        if loop is None:
            return False
        if threading.current_thread() != self._thread:
            # gevent does something bad that causes asyncio.get_running_loop() to return self._loop
            return False
        current_loop = self._get_running_loop()
        return loop == current_loop

    def _run_function_sync(self, coro):
        if self._is_inside_loop():
            raise Exception("Deadlock detected: calling a sync function from the synchronizer loop")

        loop = self._get_loop(start=True)

        inner_task_fut = concurrent.futures.Future()

        async def wrapper_coro():
            # this wrapper is needed since run_coroutine_threadsafe *only* accepts coroutines
            inner_task = loop.create_task(coro)
            inner_task_fut.set_result(inner_task)  # sends the task itself to the origin thread
            return await inner_task

        fut = asyncio.run_coroutine_threadsafe(wrapper_coro(), loop)
        try:
            while 1:
                try:
                    # repeated poll to give Windows a chance to abort on Ctrl-C
                    value = fut.result(timeout=self._future_poll_interval)
                    break
                except concurrent.futures.TimeoutError:
                    pass
        except KeyboardInterrupt as exc:
            # in case there is a keyboard interrupt while we are waiting
            # we cancel the *underlying* coro_task (unlike what fut.cancel() would do)
            # and then wait for the *wrapper* coroutine to get a result back, which
            # happens after the cancellation resolves
            if inner_task_fut.done():
                inner_task: asyncio.Task = inner_task_fut.result()
                loop.call_soon_threadsafe(inner_task.cancel)
            try:
                value = fut.result()
            except concurrent.futures.CancelledError as expected_cancellation:
                # we *expect* this cancellation, but defer to the passed coro to potentially
                # intercept and treat the cancellation some other way
                expected_cancellation.__suppress_context__ = True
                raise exc  # if cancel - re-raise the original KeyboardInterrupt again

        return value

    async def _run_function_async(self, coro):
        loop = self._get_loop(start=True)
        if self._is_inside_loop():
            value = await coro
        else:
            inner_task_fut = concurrent.futures.Future()

            async def wrapper_coro():
                inner_task = loop.create_task(coro)
                inner_task_fut.set_result(inner_task)  # sends the task itself to the origin thread
                return await inner_task

            c_fut = asyncio.run_coroutine_threadsafe(wrapper_coro(), loop)
            a_fut = asyncio.wrap_future(c_fut)

            shielded_task = None
            try:
                while 1:
                    # the loop + wait_for timeout is for windows ctrl-C compatibility since
                    # windows doesn't truly interrupt the event loop on sigint
                    try:
                        # We create a task here to prevent an anonymous task inside asyncio.wait_for that could
                        # get an unresolved timeout during cancellation handling below, resulting in a warning
                        # traceback.
                        shielded_task = asyncio.create_task(
                            asyncio.wait_for(
                                # inner shield prevents wait_for from cancelling a_fut on timeout
                                asyncio.shield(a_fut),
                                timeout=self._future_poll_interval,
                            )
                        )
                        # The outer shield prevents a cancelled caller from cancelling a_fut directly
                        # so that we can instead cancel the underlying coro_task and wait for it
                        # to bubble back up as a CancelledError gracefully between threads
                        # in order to run any cancellation logic in the coroutine
                        value = await asyncio.shield(shielded_task)
                        break
                    except asyncio.TimeoutError:
                        continue

            except asyncio.CancelledError:
                try:
                    if a_fut.cancelled():
                        raise  # cancellation came from within c_fut
                    if inner_task_fut.done():
                        inner_task: asyncio.Task = inner_task_fut.result()
                        loop.call_soon_threadsafe(inner_task.cancel)  # cancel task on synchronizer event loop
                        # wait for cancellation logic in the underlying coro to complete
                        # this should typically raise CancelledError, but in case of either:
                        # * cancellation prevention in the coro (catching the CancelledError)
                        # * coro_task resolves before the call_soon_threadsafe above is scheduled
                        # the cancellation in a_fut would be cancelled

                        await a_fut  # wait for cancellation logic to complete - this *normally* raises CancelledError
                    raise  # re-raise the CancelledError regardless - preventing unintended cancellation aborts
                finally:
                    if shielded_task:
                        shielded_task.cancel()  # cancel the shielded task, preventing timeouts

        return value

    def _run_generator_sync(self, gen):
        value, is_exc = None, False
        while True:
            try:
                if is_exc:
                    value = self._run_function_sync(gen.athrow(value))
                else:
                    value = self._run_function_sync(gen.asend(value))
            except StopAsyncIteration:
                break

            try:
                value = yield value
                is_exc = False
            except BaseException as exc:
                value = exc
                is_exc = True

    async def _run_generator_async(self, gen: typing.AsyncGenerator):
        value, is_exc = None, False
        while True:
            try:
                if is_exc:
                    value = await self._run_function_async(gen.athrow(value))
                else:
                    value = await self._run_function_async(gen.asend(value))
            except StopAsyncIteration:
                break

            try:
                value = yield value
                is_exc = False
            except BaseException as exc:
                value = exc
                is_exc = True
