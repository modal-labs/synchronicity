from .exceptions import UserCodeException, unwrap_coro_exception


def get_ctx_mgr_cls():
    class AsyncGeneratorContextManager:
        """This is basically copied (but slightly modified) from contextlib.py

        We could have just synchronized the built-in class, but it was added in Python 3.7, so
        we're including most of the logic here, in order to make it work with Python 3.6 as well.

        TODO: add back support for filter_tracebacks (doesn't work in Python 3.6)
        """

        def __init__(self, func, args, kwargs):
            self._gen = func(*args, **kwargs)

        async def __aenter__(self):
            try:
                return await self._gen.__anext__()
            except StopAsyncIteration:
                raise RuntimeError("generator didn't yield") from None

        async def __aexit__(self, typ, value, traceback):
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

    return AsyncGeneratorContextManager
