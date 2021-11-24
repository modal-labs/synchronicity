import asyncio
import atexit
import concurrent.futures
import functools
import inspect
import queue
import threading
import time
import warnings

from .contextlib import AsyncGeneratorContextManager
from .exceptions import UserCodeException, wrap_coro_exception, unwrap_coro_exception

_BUILTIN_ASYNC_METHODS = {
    "__aiter__": "__iter__",
    "__aenter__": "__enter__",
    "__aexit__": "__exit__",
}

_WRAPPED_ATTR = "_SYNCHRONICITY_HAS_WRAPPED_THIS_ALREADY"


class Synchronizer:
    """Helps you offer a blocking (synchronous) interface to asynchronous code."""

    def __init__(
        self, return_futures=False, multiwrap_warning=False, async_leakage_warning=True
    ):
        self._return_futures = return_futures
        self._multiwrap_warning = multiwrap_warning
        self._async_leakage_warning = async_leakage_warning
        self._loop = None
        self._thread = None
        atexit.register(self._close_loop)

    def __getstate__(self):
        return {
            "_return_futures": self._return_futures,
            "_multiwrap_warning": self._multiwrap_warning,
            "_async_leakage_warning": self._async_leakage_warning,
        }

    def __setstate__(self, d):
        self._return_futures = d["_return_futures"]
        self._multiwrap_warning = d["_multiwrap_warning"]
        self._async_leakage_warning = d["_async_leakage_warning"]

    def _start_loop(self, loop):
        if self._loop and self._loop.is_running():
            raise Exception("Synchronicity loop already running.")

        is_ready = threading.Event()

        def run_forever():
            self._loop = loop
            is_ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=lambda: run_forever(), daemon=True)
        self._thread.start()  # TODO: we should join the thread at some point
        is_ready.wait()  # TODO: this might block for a very short time
        return self._loop

    def _close_loop(self):
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            while self._loop.is_running():
                time.sleep(0.01)
            self._loop.close()
        if self._thread is not None:
            self._thread.join()

    def _get_loop(self):
        if self._loop is not None:
            return self._loop
        return self._start_loop(asyncio.new_event_loop())

    def _get_running_loop(self):
        if hasattr(asyncio, "get_running_loop"):
            try:
                return asyncio.get_running_loop()
            except RuntimeError:
                return
        else:
            # Python 3.6 compatibility
            return asyncio._get_running_loop()

    def _is_async_context(self):
        return bool(self._get_running_loop())

    def _wrap_check_async_leakage(self, coro):
        """Check if a coroutine returns another coroutine (or an async generator) and warn.

        The reason this is important to catch is that otherwise even synchronized code might end up
        "leaking" async code into the caller.
        """
        if not self._async_leakage_warning:
            return coro

        async def coro_wrapped():
            value = await coro
            # TODO: we should include the name of the original function here
            if inspect.iscoroutine(value):
                warnings.warn(
                    f"Potential async leakage: coroutine returned a coroutine {value}."
                )
            elif inspect.isasyncgen(value):
                warnings.warn(
                    f"Potential async leakage: Coroutine returned an async generator {value}."
                )
            return value

        return coro_wrapped()

    def _run_function_sync(self, coro, return_future):
        coro = wrap_coro_exception(coro)
        coro = self._wrap_check_async_leakage(coro)
        loop = self._get_loop()
        if return_future is None:
            return_future = self._return_futures
        if return_future:
            coro = unwrap_coro_exception(coro)  # A bit of a special case
            return asyncio.run_coroutine_threadsafe(coro, loop)
        else:
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
            return fut.result()

    async def _run_function_async(self, coro):
        coro = wrap_coro_exception(coro)
        coro = self._wrap_check_async_leakage(coro)
        current_loop = self._get_running_loop()
        loop = self._get_loop()
        if loop == current_loop:
            return await coro

        c_fut = asyncio.run_coroutine_threadsafe(coro, loop)
        a_fut = asyncio.wrap_future(c_fut)
        return await a_fut

    def _run_generator_sync(self, gen):
        value, is_exc = None, False
        while True:
            try:
                if is_exc:
                    value = self._run_function_sync(
                        gen.athrow(value), return_future=False
                    )
                else:
                    value = self._run_function_sync(
                        gen.asend(value), return_future=False
                    )
            except UserCodeException as uc_exc:
                raise uc_exc.exc from None
            except StopAsyncIteration:
                break
            try:
                value = yield value
                is_exc = False
            except BaseException as exc:
                value = exc
                is_exc = True

    async def _run_generator_async(self, gen, unwrap_user_excs=True):
        value, is_exc = None, False
        while True:
            try:
                if is_exc:
                    value = await self._run_function_async(
                        wrap_coro_exception(gen.athrow(value))
                    )
                else:
                    value = await self._run_function_async(
                        wrap_coro_exception(gen.asend(value))
                    )
            except UserCodeException as uc_exc:
                if unwrap_user_excs:
                    raise uc_exc.exc from None
                else:
                    # This is needed since contextlib uses this function as a helper
                    raise uc_exc
            except StopAsyncIteration:
                break
            try:
                value = yield value
                is_exc = False
            except BaseException as exc:
                value = exc
                is_exc = True

    def _wrap_callable(self, f, return_future=None):
        if hasattr(f, _WRAPPED_ATTR):
            if self._multiwrap_warning:
                warnings.warn(
                    f"Function {f} is already wrapped, but getting wrapped again"
                )
            return f

        @functools.wraps(f)
        def f_wrapped(*args, **kwargs):
            res = f(*args, **kwargs)
            is_async_context = self._is_async_context()
            is_coroutine = inspect.iscoroutine(res)
            is_asyncgen = inspect.isasyncgen(res)
            if is_coroutine:
                # The run_function_* may throw UserCodeExceptions that
                # need to be unwrapped here at the entrypoint
                if is_async_context:
                    coro = self._run_function_async(res)
                    coro = unwrap_coro_exception(coro)
                    return coro
                else:
                    try:
                        return self._run_function_sync(res, return_future)
                    except UserCodeException as uc_exc:
                        raise uc_exc.exc from None
            elif is_asyncgen:
                # Note that the _run_generator_* functions handle their own
                # unwrapping of exceptions (this happens during yielding)
                if is_async_context:
                    return self._run_generator_async(res)
                else:
                    return self._run_generator_sync(res)
            else:
                return res

        setattr(f_wrapped, _WRAPPED_ATTR, True)
        return f_wrapped

    def create_class(self, cls_metaclass, cls_name, cls_bases, cls_dict):
        new_dict = {}
        for k, v in cls_dict.items():
            if k in _BUILTIN_ASYNC_METHODS:
                k_sync = _BUILTIN_ASYNC_METHODS[k]
                new_dict[k] = v
                new_dict[k_sync] = self._wrap_callable(v, return_future=False)
            elif callable(v):
                new_dict[k] = self._wrap_callable(v)
            elif isinstance(v, staticmethod):
                # TODO(erikbern): this feels pretty hacky
                new_dict[k] = staticmethod(self._wrap_callable(v.__func__))
            elif isinstance(v, classmethod):
                # TODO(erikbern): this feels pretty hacky
                new_dict[k] = classmethod(self._wrap_callable(v.__func__))
            else:
                new_dict[k] = v
        return type.__new__(cls_metaclass, cls_name, cls_bases, new_dict)

    def _wrap_class(self, cls):
        cls_metaclass = type
        cls_name = cls.__name__
        cls_bases = (cls,)
        cls_dict = cls.__dict__
        return self.create_class(cls_metaclass, cls_name, cls_bases, cls_dict)

    def __call__(self, object):
        if inspect.isclass(object):
            return self._wrap_class(object)
        elif callable(object):
            return self._wrap_callable(object)
        else:
            raise Exception("Argument %s is not a class or a callable" % object)

    def asynccontextmanager(self, func):
        @functools.wraps(func)
        def helper(*args, **kwargs):
            return AsyncGeneratorContextManager(self, func, args, kwargs)

        return helper
