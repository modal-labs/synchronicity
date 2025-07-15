import asyncio
import atexit
import concurrent.futures
import os
import threading
import types
import typing
from typing import Callable, Optional

T = typing.TypeVar("T", bound=typing.Union[type, Callable])

# Global registry for synchronizer instances
_synchronizer_registry = {}


def get_synchronizer(name: str) -> "Synchronizer":
    """Get or create a synchronizer instance by name from the global registry."""
    if name not in _synchronizer_registry:
        _synchronizer_registry[name] = Synchronizer()
    return _synchronizer_registry[name]


class Synchronizer:
    def __init__(self):
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

    async def _run_generator_async(self, gen):
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


class Library:
    def __init__(self, synchronizer_name: str):
        self._synchronizer_name = synchronizer_name
        self._wrapped = {}

    def wrap(self, *, target_module: Optional[str] = None) -> typing.Callable[[T], T]:
        def decorator(class_or_function: T) -> T:
            if target_module is None:
                current_module = class_or_function.__module__.split(".")
                assert current_module[-1].startswith("_")
                output_module = current_module[:-1] + [current_module[-1].removeprefix("_")]
                output_module = ".".join(output_module)
            else:
                output_module = target_module

            self._wrapped[class_or_function] = (output_module, class_or_function.__name__)

        return decorator

    def _compile_function(self, f: types.FunctionType, target_module: str) -> str:
        import inspect
        import typing

        # Get function signature and annotations
        sig = inspect.signature(f)
        return_annotation = sig.return_annotation

        # Check if it's an async generator
        is_async_generator = (
            hasattr(return_annotation, "__origin__") and return_annotation.__origin__ is typing.AsyncGenerator
        )

        # Build the function signature with type annotations
        params = []
        for name, param in sig.parameters.items():
            param_str = name
            if param.annotation != param.empty:
                # Format annotation properly
                if hasattr(param.annotation, "__module__") and hasattr(param.annotation, "__name__"):
                    if param.annotation.__module__ in ("builtins", "__builtin__"):
                        annotation_str = param.annotation.__name__
                    else:
                        annotation_str = f"{param.annotation.__module__}.{param.annotation.__name__}"
                else:
                    annotation_str = repr(param.annotation)
                param_str += f": {annotation_str}"

            if param.default is not param.empty:
                default_val = repr(param.default)
                param_str += f" = {default_val}"

            params.append(param_str)

        param_str = ", ".join(params)

        # Format return annotation
        if return_annotation != sig.empty:
            if hasattr(return_annotation, "__module__") and hasattr(return_annotation, "__name__"):
                if return_annotation.__module__ in ("builtins", "__builtin__"):
                    return_annotation_str = return_annotation.__name__
                else:
                    return_annotation_str = f"{return_annotation.__module__}.{return_annotation.__name__}"
            else:
                return_annotation_str = repr(return_annotation)

            # For async functions, remove the Awaitable wrapper for the sync version
            if return_annotation_str.startswith("typing.Awaitable[") and return_annotation_str.endswith("]"):
                sync_return_annotation = return_annotation_str[17:-1]  # Remove "typing.Awaitable[" and "]"
            elif hasattr(return_annotation, "__origin__") and return_annotation.__origin__ is typing.Awaitable:
                # Extract the inner type from Awaitable[T]
                if return_annotation.__args__:
                    inner_type = return_annotation.__args__[0]
                    if hasattr(inner_type, "__module__") and hasattr(inner_type, "__name__"):
                        if inner_type.__module__ in ("builtins", "__builtin__"):
                            sync_return_annotation = inner_type.__name__
                        else:
                            sync_return_annotation = f"{inner_type.__module__}.{inner_type.__name__}"
                    else:
                        sync_return_annotation = repr(inner_type)
                else:
                    sync_return_annotation = return_annotation_str
            else:
                sync_return_annotation = return_annotation_str

            sync_return_str = f" -> {sync_return_annotation}"
            async_return_str = f" -> {return_annotation_str}"
        else:
            sync_return_str = ""
            async_return_str = ""

        # Determine which method to use based on return type
        if is_async_generator:
            method_name = "_run_generator_sync"
            async_method_name = "_run_generator_async"
        else:
            method_name = "_run_function_sync"
            async_method_name = "_run_function_async"

        # Get the function arguments for calling the original function
        call_args = []
        for name, param in sig.parameters.items():
            call_args.append(name)
        call_args_str = ", ".join(call_args)

        # Generate the class-based wrapper code
        class_name = f"_{f.__name__}Wrapper"
        sync_code = f"""class {class_name}:
    synchronizer = get_synchronizer('{self._synchronizer_name}')
    impl_function = {target_module}.{f.__name__}  # reference to original function

    def __call__(self, {param_str}){sync_return_str}:
        coro = self.impl_function({call_args_str})
        raw_result = self.synchronizer.{method_name}(coro)
        return raw_result

    async def aio(self, {param_str}){async_return_str}:
        coro = self.impl_function({call_args_str})
        raw_result = await self.synchronizer.{async_method_name}(coro)
        return raw_result

{f.__name__} = {class_name}()"""

        return sync_code

    def compile(self) -> str:
        for o, (target_module, target_name) in self._wrapped.items():
            print(target_module, target_name, o)
            if isinstance(o, types.FunctionType):
                print(self._compile_function(o, target_module))
