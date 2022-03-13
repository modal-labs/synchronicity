from .exceptions import UserCodeException, unwrap_coro_exception
from .interface import Interface


class AsyncGeneratorContextManager:
    """This is basically copied (but slightly modified) from contextlib.py

    We could have just synchronized the built-in class, but it was added in Python 3.7, so
    we're including most of the logic here, in order to make it work with Python 3.6 as well.

    TODO: add back support for filter_tracebacks (doesn't work in Python 3.6)
    """

    def __init__(self, synchronizer, interface, func, args, kwargs):
        self._synchronizer = synchronizer
        self._interface = interface

        # Run it in the correct thread
        self._gen = synchronizer._run_generator_async(
            func(*args, **kwargs), self._interface, unwrap_user_excs=False
        )

    async def _enter(self):
        try:
            return await self._gen.__anext__()
        except StopAsyncIteration:
            raise RuntimeError("generator didn't yield") from None

    async def _exit(self, typ, value, traceback):
        if typ is None:
            try:
                await self._gen.__anext__()
            except StopAsyncIteration:
                return False
            else:
                raise RuntimeError("generator didn't stop")
        else:
            if value is None:
                value = typ()
            try:
                ret = self._gen.athrow(typ, value, traceback)
                await ret
            except StopAsyncIteration as exc:
                return exc is not value
            except RuntimeError as exc:
                if exc is value:
                    return False
                if (
                    isinstance(value, (StopIteration, StopAsyncIteration))
                    and exc.__cause__ is value
                ):
                    return False
                raise
            except BaseException as exc:
                if exc is not value:
                    raise
                return False
            raise RuntimeError("generator didn't stop after athrow()")

    # Actual methods

    def __aenter__(self):
        coro = self._enter()
        coro = self._synchronizer._run_function_async(coro, self._interface)
        coro = unwrap_coro_exception(coro)
        return coro

    def __enter__(self):
        runtime_interface = self._synchronizer._get_runtime_interface(self._interface)
        if runtime_interface == Interface.ASYNC:
            raise RuntimeError(
                "Attempt to use 'with' in async code. Did you mean 'async with'?"
            )
        try:
            return self._synchronizer._run_function_sync(self._enter(), self._interface)
        except UserCodeException as uc_exc:
            raise uc_exc.exc from None

    def __aexit__(self, typ, value, traceback):
        coro = self._exit(typ, value, traceback)
        coro = self._synchronizer._run_function_async(coro, self._interface)
        coro = unwrap_coro_exception(coro)
        return coro

    def __exit__(self, typ, value, traceback):
        try:
            return self._synchronizer._run_function_sync(
                self._exit(typ, value, traceback),
                self._interface,
            )
        except UserCodeException as uc_exc:
            raise uc_exc.exc from None
