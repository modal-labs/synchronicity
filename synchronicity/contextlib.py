import sys
from .exceptions import UserCodeException, unwrap_coro_exception


def get_ctx_mgr_cls():
    class AsyncGeneratorContextManager:
        """This is basically copied (but slightly modified) from contextlib.py

        TODO: maybe let's just synchronize the contextlib class? We didn't do it previously
        since it was added in 3.7 and we wanted to offer it for 3.6, but we don't support
        3.6 now anyway.

        TODO: add back support for filter_tracebacks
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
                if sys.version_info < (3, 7, 9) and typ == GeneratorExit:
                    # fix for weird error pre 3.7.9 https://bugs.python.org/issue33786
                    # not sure if it breaks something else though so lets version gate it
                    typ = StopAsyncIteration
                    value = typ()

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
