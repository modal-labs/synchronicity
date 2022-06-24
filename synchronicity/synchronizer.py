import asyncio
import atexit
import functools
import inspect
import threading
import time
import warnings

from .callback import Callback
from .async_wrap import wraps_by_interface, async_compat_wraps
from .contextlib import get_ctx_mgr_cls
from .exceptions import UserCodeException, unwrap_coro_exception, wrap_coro_exception
from .interface import Interface

_BUILTIN_ASYNC_METHODS = {
    "__aiter__": "__iter__",
    "__aenter__": "__enter__",
    "__aexit__": "__exit__",
}

_RETURN_FUTURE_KWARG = "_future"

# For classes and functions
_WRAPPED_ATTR = "_SYNCHRONICITY_WRAPPED_CLS"
_ORIGINAL_ATTR = "_SYNCHRONICITY_ORIGINAL_CLS"

# For instances
_WRAPPED_INST_ATTR = "_SYNCHRONICITY_WRAPPED_INST"
_ORIGINAL_INST_ATTR = "_SYNCHRONICITY_ORIGINAL_INST"

# Default names for classes
_CLASS_PREFIXES = {
    Interface.AUTODETECT: "Auto",
    Interface.BLOCKING: "Blocking",
    Interface.ASYNC: "Async",
}

# Default names for functions
_FUNCTION_PREFIXES = {
    Interface.AUTODETECT: "auto_",
    Interface.BLOCKING: "blocking_",
    Interface.ASYNC: "async_",
}


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
        self._stopping = None

        # Prep a synchronized context manager
        self._ctx_mgr_cls = get_ctx_mgr_cls()
        self.create(self._ctx_mgr_cls)

        atexit.register(self._close_loop)

    _PICKLE_ATTRS = [
        "_multiwrap_warning",
        "_async_leakage_warning",
    ]

    def get_name(self, object, interface):
        # TODO: make it possible to override this
        if inspect.isclass(object):
            return _CLASS_PREFIXES[interface] + object.__name__
        elif inspect.isfunction(object):
            return _FUNCTION_PREFIXES[interface] + object.__name__
        else:
            raise Exception("Can only compute names for classes and functions")

    def __getstate__(self):
        return dict([(attr, getattr(self, attr)) for attr in self._PICKLE_ATTRS])

    def __setstate__(self, d):
        for attr in self._PICKLE_ATTRS:
            setattr(self, attr, d[attr])

    def _start_loop(self):
        if self._loop and self._loop.is_running():
            raise Exception("Synchronicity loop already running.")

        is_ready = threading.Event()

        def thread_inner():
            async def loop_inner():
                self._loop = asyncio.get_running_loop()
                self._stopping = asyncio.Event()
                is_ready.set()
                await self._stopping.wait()  # wait until told to stop

            asyncio.run(loop_inner())

        self._thread = threading.Thread(target=thread_inner, daemon=True)
        self._thread.start()
        is_ready.wait()  # TODO: this might block for a very short time
        return self._loop

    def _close_loop(self):
        if self._thread is not None:
            if not self._loop.is_closed():
                # This also serves the purpose of waking up an idle loop
                self._loop.call_soon_threadsafe(self._stopping.set)
            self._thread.join()

    def _get_loop(self, start=False):
        if self._loop is None and start:
            return self._start_loop()
        return self._loop

    def _get_running_loop(self):
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return

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
        interface_instances = object.__dict__.setdefault(_WRAPPED_INST_ATTR, {})
        if interface not in interface_instances:
            cls_dct = object.__class__.__dict__
            interfaces = cls_dct[_WRAPPED_ATTR]
            interface_cls = interfaces[interface]
            new_object = interface_cls.__new__(interface_cls)
            interface_instances[interface] = new_object
            # Store a reference to the original object
            new_object.__dict__[_ORIGINAL_INST_ATTR] = object
        return interface_instances[interface]

    def _translate_scalar_in(self, object):
        # If it's an external object, translate it to the internal type
        if hasattr(object, "__dict__"):
            if inspect.isclass(object):  # TODO: functions?
                return object.__dict__.get(_ORIGINAL_ATTR, object)
            else:
                return object.__dict__.get(_ORIGINAL_INST_ATTR, object)
        else:
            return object

    def _translate_scalar_out(self, object, interface):
        # If it's an internal object, translate it to the external interface
        if inspect.isclass(object):  # TODO: functions?
            cls_dct = object.__dict__
            if _WRAPPED_ATTR in cls_dct:
                return cls_dct[_WRAPPED_ATTR][interface]
            else:
                return object
        else:
            cls_dct = object.__class__.__dict__
            if _WRAPPED_ATTR in cls_dct:
                # This is an *instance* of a synchronized class, translate its type
                return self._wrap_instance(object, interface)
            else:
                return object

    def _recurse_map(self, mapper, object):
        if type(object) == list:
            return list(self._recurse_map(mapper, item) for item in object)
        elif type(object) == tuple:
            return tuple(self._recurse_map(mapper, item) for item in object)
        elif type(object) == dict:
            return dict(
                (key, self._recurse_map(mapper, item)) for key, item in object.items()
            )
        else:
            return mapper(object)

    def _translate_in(self, object):
        return self._recurse_map(self._translate_scalar_in, object)

    def _translate_out(self, object, interface):
        return self._recurse_map(
            lambda scalar: self._translate_scalar_out(scalar, interface), object
        )

    def _translate_coro_out(self, coro, interface):
        async def unwrap_coro():
            return self._translate_out(await coro, interface)

        return unwrap_coro()

    def _run_function_sync(self, coro, interface):
        current_loop = self._get_running_loop()
        loop = self._get_loop()
        if loop is not None and loop == current_loop:
            raise Exception(
                "Deadlock detected: calling a sync function from the synchronizer loop"
            )

        coro = wrap_coro_exception(coro)
        coro = self._wrap_check_async_leakage(coro)
        loop = self._get_loop(start=True)
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        value = fut.result()
        return self._translate_out(value, interface)

    def _run_function_sync_future(self, coro, interface):
        coro = wrap_coro_exception(coro)
        coro = self._wrap_check_async_leakage(coro)
        loop = self._get_loop(start=True)
        # For futures, we unwrap the result at this point, not in f_wrapped
        coro = unwrap_coro_exception(coro)
        coro = self._translate_coro_out(coro, interface)
        return asyncio.run_coroutine_threadsafe(coro, loop)

    async def _run_function_async(self, coro, interface):
        coro = wrap_coro_exception(coro)
        coro = self._wrap_check_async_leakage(coro)
        current_loop = self._get_running_loop()
        loop = self._get_loop(start=True)
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

    def create_callback(self, f, interface):
        return Callback(self, f, interface)

    def _update_wrapper(self, f_wrapped, f, name=None):
        """Very similar to functools.update_wrapper"""
        functools.update_wrapper(f_wrapped, f)
        if name is not None:
            f_wrapped.__name__ = name
            f_wrapped.__qualname__ = name

    def _wrap_callable(self, f, interface, name=None, allow_futures=True):
        if hasattr(f, _ORIGINAL_ATTR):
            if self._multiwrap_warning:
                warnings.warn(
                    f"Function {f} is already wrapped, but getting wrapped again"
                )
            return f

        @wraps_by_interface(interface, f)
        def f_wrapped(*args, **kwargs):
            return_future = kwargs.pop(_RETURN_FUTURE_KWARG, False)

            # If this gets called with an argument that represents an external type,
            # translate it into an internal type
            args = self._translate_in(args)
            kwargs = self._translate_in(kwargs)

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
                if inspect.isfunction(res) or isinstance(
                    res, functools.partial
                ):  # TODO: HACKY HACK
                    # TODO: this is needed for decorator wrappers that returns functions
                    # Maybe a bit of a hacky special case that deserves its own decorator
                    @wraps_by_interface(interface, res)
                    def f_wrapped(*args, **kwargs):
                        args = self._translate_in(args)
                        kwargs = self._translate_in(kwargs)
                        f_res = res(*args, **kwargs)
                        return self._translate_out(f_res, interface)

                    return f_wrapped

                return self._translate_out(res, interface)

        self._update_wrapper(f_wrapped, f, name)
        setattr(f_wrapped, _ORIGINAL_ATTR, f)
        return f_wrapped

    def _wrap_proxy_method(self, method, interface, allow_futures=True):
        method = self._wrap_callable(method, interface, allow_futures=allow_futures)

        @wraps_by_interface(interface, method)
        def proxy_method(self, *args, **kwargs):
            instance = self.__dict__[_ORIGINAL_INST_ATTR]
            return method(instance, *args, **kwargs)

        return proxy_method

    def _wrap_proxy_staticmethod(self, method, interface):
        method = self._wrap_callable(method.__func__, interface)
        return staticmethod(method)

    def _wrap_proxy_classmethod(self, method, interface):
        method = self._wrap_callable(method.__func__, interface)

        @wraps_by_interface(interface, method)
        def proxy_classmethod(wrapped_cls, *args, **kwargs):
            return method(wrapped_cls, *args, **kwargs)

        return classmethod(proxy_classmethod)

    def _wrap_proxy_property(self, prop, interface):
        kwargs = {}
        for attr in ["fget", "fset", "fdel"]:
            if getattr(prop, attr):
                func = getattr(prop, attr)
                kwargs[attr] = self._wrap_proxy_method(func, interface, False)
        return property(**kwargs)

    def _wrap_proxy_constructor(self, cls, interface):
        """Returns a custom __init__ for the subclass."""

        def my_init(wrapped_self, *args, **kwargs):
            # Create base instance
            args = self._translate_in(args)
            kwargs = self._translate_in(kwargs)
            instance = cls(*args, **kwargs)

            # Register self as the wrapped one
            interface_instances = {interface: wrapped_self}
            instance.__dict__[_WRAPPED_INST_ATTR] = interface_instances

            # Store a reference to the original object
            wrapped_self.__dict__[_ORIGINAL_INST_ATTR] = instance

        self._update_wrapper(my_init, cls.__init__)
        return my_init

    def _wrap_class(self, cls, interface, name):
        if name is None:
            name = cls.__name__
        bases = tuple(
            self._wrap_class_or_function(base, interface) if base != object else object
            for base in cls.__bases__
        )
        new_dict = {_ORIGINAL_ATTR: cls}
        if cls is not None:
            new_dict["__init__"] = self._wrap_proxy_constructor(cls, interface)
        for k, v in cls.__dict__.items():
            if k in _BUILTIN_ASYNC_METHODS:
                k_sync = _BUILTIN_ASYNC_METHODS[k]
                if interface in (Interface.BLOCKING, Interface.AUTODETECT):
                    new_dict[k_sync] = self._wrap_proxy_method(
                        v, interface, allow_futures=False
                    )
                if interface in (Interface.ASYNC, Interface.AUTODETECT):
                    new_dict[k] = self._wrap_proxy_method(
                        v, interface, allow_futures=False
                    )
            elif k in ("__new__", "__init__"):
                # Skip custom constructor in the wrapped class
                # Instead, delegate to the base class constructor and wrap it
                pass
            elif isinstance(v, staticmethod):
                # TODO(erikbern): this feels pretty hacky
                new_dict[k] = self._wrap_proxy_staticmethod(v, interface)
            elif isinstance(v, classmethod):
                new_dict[k] = self._wrap_proxy_classmethod(v, interface)
            elif isinstance(v, property):
                new_dict[k] = self._wrap_proxy_property(v, interface)
            elif callable(v):
                new_dict[k] = self._wrap_proxy_method(v, interface)

        new_cls = type.__new__(type, name, bases, new_dict)
        new_cls.__module__ = cls.__module__
        new_cls.__doc__ = cls.__doc__
        return new_cls

    def _wrap_class_or_function(self, object, interface):
        if _WRAPPED_ATTR not in object.__dict__:
            setattr(object, _WRAPPED_ATTR, {})

        interfaces = object.__dict__[_WRAPPED_ATTR]
        if interface in interfaces:
            if self._multiwrap_warning:
                warnings.warn(
                    f"Object {object} is already wrapped, but getting wrapped again"
                )
            return interfaces[interface]

        name = self.get_name(object, interface)
        if inspect.isclass(object):
            new_object = self._wrap_class(object, interface, name)
        elif inspect.isfunction(object):
            new_object = self._wrap_callable(object, interface, name)
        else:
            raise Exception("Argument %s is not a class or a callable" % object)
        interfaces[interface] = new_object
        return new_object

    def asynccontextmanager(self, func):
        @functools.wraps(func)
        def helper(*args, **kwargs):
            return self._ctx_mgr_cls(func, args, kwargs)

        return helper

    # New interface that (almost) doesn't mutate objects

    def create(self, object):  # TODO: this should really be __call__ later
        if inspect.isclass(object) or inspect.isfunction(object):
            # This is a class/function, for which we cache the interfaces
            interfaces = {}
            for interface in Interface:
                interfaces[interface] = self._wrap_class_or_function(object, interface)
            return interfaces
        elif _WRAPPED_ATTR in object.__class__.__dict__:
            # TODO: this requires that the class is already synchronized
            interfaces = {}
            for interface in Interface:
                interfaces[interface] = self._wrap_instance(object, interface)
        else:
            raise Exception(
                "Can only wrap classes, functions, and instances of synchronized classes"
            )
        return interfaces

    def is_synchronized(self, object):
        if inspect.isclass(object) or inspect.isfunction(object):
            return hasattr(object, _ORIGINAL_ATTR)
        else:
            return hasattr(object.__class__, _ORIGINAL_ATTR)

    # Old interface that we should consider purging

    def __call__(self, object):
        interfaces = self.create(object)
        return interfaces[Interface.AUTODETECT]
