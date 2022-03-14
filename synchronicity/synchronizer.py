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
from .exceptions import UserCodeException, unwrap_coro_exception, wrap_coro_exception
from .interface import Interface

_BUILTIN_ASYNC_METHODS = {
    "__aiter__": "__iter__",
    "__aenter__": "__enter__",
    "__aexit__": "__exit__",
}

_WRAPPED_ATTR = "_SYNCHRONICITY_HAS_WRAPPED_THIS_ALREADY"
_RETURN_FUTURE_KWARG = "_future"

_WRAPPED_CLS_ATTR = "_SYNCHRONICITY_WRAPPED_CLS"
_ORIGINAL_CLS_ATTR = "_SYNCHRONICITY_ORIGINAL_CLS"

_WRAPPED_INST_ATTR = "_SYNCHRONICITY_WRAPPED_INST"
_ORIGINAL_INST_ATTR = "_SYNCHRONICITY_ORIGINAL_INST"


class Synchronizer:
    """Helps you offer a blocking (synchronous) interface to asynchronous code."""

    def __init__(
        self,
        multiwrap_warning=False,
        async_leakage_warning=True,
    ):
        self._multiwrap_warning = multiwrap_warning
        self._async_leakage_warning = async_leakage_warning
        self._loop = None
        self._thread = None
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

    def _get_runtime_interface(self, interface):
        """Returns one out of Interface.ASYNC or Interface.BLOCKING"""
        if interface == Interface.AUTODETECT:
            return Interface.ASYNC if self._get_running_loop() else Interface.BLOCKING
        else:
            assert interface in (Interface.ASYNC, Interface.BLOCKING)
            return interface

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

    def _wrap_instance(self, object, interface):
        # Takes an object and creates a new proxy object for it
        # They will share the same underlying __dict__
        interface_instances = object.__dict__.setdefault(_WRAPPED_INST_ATTR, {})
        if interface not in interface_instances:
            cls_dct = object.__class__.__dict__
            interfaces = cls_dct[_WRAPPED_CLS_ATTR]
            interface_cls = interfaces[interface]
            new_object = object.__new__(interface_cls)
            new_object.__dict__ = object.__dict__
            interface_instances[interface] = new_object
        return interface_instances[interface]

    def _translate_in(self, object):
        # If it's an external object, translate it to the internal type
        if inspect.isclass(object):  # TODO: functions?
            return getattr(object, _ORIGINAL_CLS_ATTR, object)
        else:
            return getattr(object, _ORIGINAL_INST_ATTR, object)

    def _translate_out(self, object, interface):
        # If it's an internal object, translate it to the external interface
        if inspect.isclass(object):  # TODO: functions?
            cls_dct = object.__dict__
            if _WRAPPED_CLS_ATTR in cls_dct:
                return cls_dct[_WRAPPED_CLS_ATTR][interface]
            else:
                return object
        else:
            cls_dct = object.__class__.__dict__
            if _WRAPPED_CLS_ATTR in cls_dct:
                # This is an *instance* of a synchronized class, translate its type
                return self._wrap_instance(object, interface)
            else:
                return object

    def _translate_coro_out(self, coro, interface):
        async def unwrap_coro():
            return self._translate_out(await coro, interface)

        return unwrap_coro()

    def _run_function_sync(self, coro, interface):
        coro = wrap_coro_exception(coro)
        coro = self._wrap_check_async_leakage(coro)
        loop = self._get_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        value = fut.result()
        return self._translate_out(value, interface)

    def _run_function_sync_future(self, coro, interface):
        coro = wrap_coro_exception(coro)
        coro = self._wrap_check_async_leakage(coro)
        loop = self._get_loop()
        # For futures, we unwrap the result at this point, not in f_wrapped
        coro = unwrap_coro_exception(coro)
        coro = self._translate_coro_out(coro, interface)
        return asyncio.run_coroutine_threadsafe(coro, loop)

    async def _run_function_async(self, coro, interface):
        coro = wrap_coro_exception(coro)
        coro = self._wrap_check_async_leakage(coro)
        current_loop = self._get_running_loop()
        loop = self._get_loop()
        if loop == current_loop:
            value = await coro
        else:
            c_fut = asyncio.run_coroutine_threadsafe(coro, loop)
            a_fut = asyncio.wrap_future(c_fut)
            value = await a_fut
        return self._translate_out(value, interface)

    def _run_generator_sync(self, gen, interface):
        value, is_exc = None, False
        while True:
            try:
                if is_exc:
                    value = self._run_function_sync(gen.athrow(value), interface)
                else:
                    value = self._run_function_sync(gen.asend(value), interface)
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

    async def _run_generator_async(self, gen, interface, unwrap_user_excs=True):
        value, is_exc = None, False
        while True:
            try:
                if is_exc:
                    value = await self._run_function_async(gen.athrow(value), interface)
                else:
                    value = await self._run_function_async(gen.asend(value), interface)
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

    def _wrap_callable(self, f, interface, allow_futures=True):
        if hasattr(f, _WRAPPED_ATTR):
            if self._multiwrap_warning:
                warnings.warn(
                    f"Function {f} is already wrapped, but getting wrapped again"
                )
            return f

        @functools.wraps(f)
        def f_wrapped(*args, **kwargs):
            return_future = kwargs.pop(_RETURN_FUTURE_KWARG, False)

            # If this gets called with an argument that represents an external type,
            # translate it into an internal type
            args = tuple(self._translate_in(arg) for arg in args)
            kwargs = dict((key, self._translate_in(arg)) for key, arg in kwargs.items())

            # Call the function
            res = f(*args, **kwargs)

            # Figure out if this is a coroutine or something
            is_coroutine = inspect.iscoroutine(res)
            is_asyncgen = inspect.isasyncgen(res)
            runtime_interface = self._get_runtime_interface(interface)

            if return_future:
                if not allow_futures:
                    raise Exception("Can not return future for this function")
                elif is_coroutine:
                    return self._run_function_sync_future(res, interface)
                elif is_asyncgen:
                    raise Exception("Can not return futures for generators")
                else:
                    return res
            elif is_coroutine:
                # The run_function_* may throw UserCodeExceptions that
                # need to be unwrapped here at the entrypoint
                if runtime_interface == Interface.ASYNC:
                    if self._get_running_loop() == self._get_loop():
                        # See #27. This is a bit of a hack needed to "shortcut" the exception
                        # handling if we're within the same loop - there's no need to wrap and
                        # unwrap the exception and it just adds unnecessary traceback spam.

                        # TODO(erikbern): I don't this should ever happen other than in weird cases
                        # like how we set the thread loop for pytest to the one in synchronicity
                        # during Modal tests
                        return self._translate_coro_out(res, interface)

                    coro = self._run_function_async(res, interface)
                    coro = unwrap_coro_exception(coro)
                    return coro
                elif runtime_interface == Interface.BLOCKING:
                    try:
                        return self._run_function_sync(res, interface)
                    except UserCodeException as uc_exc:
                        raise uc_exc.exc from None
            elif is_asyncgen:
                # Note that the _run_generator_* functions handle their own
                # unwrapping of exceptions (this happens during yielding)
                if runtime_interface == Interface.ASYNC:
                    return self._run_generator_async(res, interface)
                elif runtime_interface == Interface.BLOCKING:
                    return self._run_generator_sync(res, interface)
            else:
                if inspect.isfunction(res):
                    # TODO: this is needed for decorator wrappers that returns functions
                    # Maybe a bit of a hacky special case that deserves its own decorator
                    @functools.wraps(res)
                    def f_wrapped(*args, **kwargs):
                        return self._translate_out(res(*args, **kwargs), interface)

                    return f_wrapped

                return self._translate_out(res, interface)

        setattr(f_wrapped, _WRAPPED_ATTR, True)
        return f_wrapped

    def _wrap_constructor(self, cls, interface):
        """Returns a custom __new__ for the subclass."""
        def my_new(wrapped_cls, *args, **kwargs):
            base_class_instance = cls(*args, **kwargs)
            wrapped_instance = self._wrap_instance(base_class_instance, interface)
            return wrapped_instance

        return my_new

    def create_class(
        self,
        cls_metaclass,
        cls_name,
        cls_bases,
        cls_dict,
        wrapped_cls=None,
        interface=Interface.AUTODETECT,
    ):
        new_dict = {_WRAPPED_ATTR: True}
        if wrapped_cls is not None:
            new_dict["__new__"] = self._wrap_constructor(wrapped_cls, interface)
        for k, v in cls_dict.items():
            if k in _BUILTIN_ASYNC_METHODS:
                k_sync = _BUILTIN_ASYNC_METHODS[k]
                new_dict[k] = v
                new_dict[k_sync] = self._wrap_callable(
                    v, interface, allow_futures=False
                )
            elif k == "__new__":
                # Skip custom __new__ in the wrapped class
                # Instead, delegate to the base class constructor and wrap it
                pass
            elif callable(v):
                new_dict[k] = self._wrap_callable(v, interface)
            elif isinstance(v, staticmethod):
                # TODO(erikbern): this feels pretty hacky
                new_dict[k] = staticmethod(self._wrap_callable(v.__func__, interface))
            elif isinstance(v, classmethod):
                # TODO(erikbern): this feels pretty hacky
                new_dict[k] = classmethod(self._wrap_callable(v.__func__, interface))
            else:
                new_dict[k] = v
        return type.__new__(cls_metaclass, cls_name, cls_bases, new_dict)

    def _wrap_class(self, cls, interface):
        cls_metaclass = type
        cls_name = cls.__name__
        cls_bases = (cls,)
        cls_dict = cls.__dict__
        return self.create_class(
            cls_metaclass, cls_name, cls_bases, cls_dict, cls, interface
        )

    def _wrap(self, object, interface):
        if inspect.isclass(object):
            new_object = self._wrap_class(object, interface)
        elif inspect.isfunction(object):
            new_object = self._wrap_callable(object, interface)
        else:
            raise Exception("Argument %s is not a class or a callable" % object)
        setattr(new_object, _ORIGINAL_CLS_ATTR, object)
        return new_object

    def asynccontextmanager(self, func, interface=Interface.AUTODETECT):
        # TODO(erikbern): enforce defining the interface type

        @functools.wraps(func)
        def helper(*args, **kwargs):
            return AsyncGeneratorContextManager(self, interface, func, args, kwargs)

        return helper

    # New interface that doesn't mutate objects

    def mark(self, object):
        # We can't use hasattr here because it might read the attribute on a parent class
        dct = object.__dict__
        if _WRAPPED_CLS_ATTR in dct:
            pass  # TODO: we should warn here
        interfaces = dict(
            [(interface, self._wrap(object, interface)) for interface in Interface]
        )
        # Setattr always writes to object.__dict__
        setattr(object, _WRAPPED_CLS_ATTR, interfaces)
        return object

    def get(self, object, interface):
        cls_dct = object.__class__.__dict__
        dct = object.__dict__
        if _WRAPPED_CLS_ATTR in cls_dct:
            # This is an *instance* of a synchronized class, translate its type
            return self._wrap_instance(object, interface)
        if _WRAPPED_CLS_ATTR in dct:
            # This is a class or function, return the synchronized version
            return dct[_WRAPPED_CLS_ATTR][interface]
        else:
            raise Exception(f"Class/function {object} has not been registered")

    def get_async(self, object):
        return self.get(object, Interface.ASYNC)

    def get_blocking(self, object):
        return self.get(object, Interface.BLOCKING)

    def get_autodetect(self, object):
        # TODO(erikbern): deprecate?
        return self.get(object, Interface.AUTODETECT)

    def is_synchronized(self, object):
        return getattr(object, _WRAPPED_ATTR, False)

    # Old interface that we should consider purging

    def __call__(self, object):
        self.mark(object)
        wrapped = self.get(object, Interface.AUTODETECT)
        return wrapped
