from .exceptions import UserCodeException


class AsyncGeneratorContextManager:
    """This is basically copied (but slightly modified) from contextlib.py

    We could have just synchronized the built-in class, but it was added in Python 3.7, so
    we're including most of the logic here, in order to make it work with Python 3.6 as well.

    TODO: add back support for filter_tracebacks (doesn't work in Python 3.6)
    """

    def __init__(self, synchronizer, func, args, kwargs):
        self.synchronizer = synchronizer
        # Run it in the correct thread
        self.gen = synchronizer._run_generator_async(
            func(*args, **kwargs), unwrap_user_excs=False
        )

    async def _enter(self):
        try:
            return await self.gen.__anext__()
        except StopAsyncIteration:
            raise RuntimeError("generator didn't yield") from None

    async def _exit(self, typ, value, traceback):
        if typ is None:
            try:
                await self.gen.__anext__()
            except StopAsyncIteration:
                return False
            else:
                raise RuntimeError("generator didn't stop")
        else:
            if value is None:
                value = typ()
            try:
                ret = self.gen.athrow(typ, value, traceback)
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

    async def __aenter__(self):
        try:
            return await self.synchronizer._run_function_async(self._enter())
        except UserCodeException as uc_exc:
            raise uc_exc.exc from None

    def __enter__(self):
        try:
            return self.synchronizer._run_function_sync(self._enter(), False)
        except UserCodeException as uc_exc:
            raise uc_exc.exc from None

    async def __aexit__(self, typ, value, traceback):
        try:
            return await self.synchronizer._run_function_async(
                self._exit(typ, value, traceback)
            )
        except UserCodeException as uc_exc:
            raise uc_exc.exc from None

    def __exit__(self, typ, value, traceback):
        try:
            return self.synchronizer._run_function_sync(
                self._exit(typ, value, traceback), False
            )
        except UserCodeException as uc_exc:
            raise uc_exc.exc from None
