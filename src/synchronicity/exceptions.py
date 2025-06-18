import asyncio
import concurrent.futures
import os
import sys
from pathlib import Path
from types import TracebackType
from typing import Optional

import synchronicity


class UserCodeException(Exception):
    """This is used to wrap and unwrap exceptions in "user code".

    This lets us have cleaner tracebacks without all the internal synchronicity stuff."""

    def __init__(self, exc):
        # There's always going to be one place inside synchronicity where we
        # catch the exception. We can always safely remove that frame from the
        # traceback.
        self.exc = exc


def wrap_coro_exception(coro):
    async def coro_wrapped():
        try:
            return await coro
        except StopAsyncIteration:
            raise
        except asyncio.CancelledError:
            # we don't want to wrap these since cancelled Task's are otherwise
            # not properly marked as cancelled, and then not treated correctly
            # during event loop shutdown (perhaps in other places too)
            raise
        except UserCodeException:
            raise  # Pass-through in case it got double-wrapped
        except Exception as exc:
            if sys.version_info < (3, 11) and os.getenv("SYNCHRONICITY_TRACEBACK", "0") != "1":
                # We do some wrap/unwrap hacks on exceptions in <Python 3.11 which
                # cleans up *some* of the internal traceback frames
                exc.with_traceback(exc.__traceback__.tb_next)
                raise UserCodeException(exc)
            raise
        except BaseException as exc:
            # special case if a coroutine raises a KeyboardInterrupt or similar
            # exception that would otherwise kill the event loop.
            # Not sure if this is wise tbh, but there is a unit test that checks
            # for KeyboardInterrupt getting propagated, which would require this
            raise UserCodeException(exc)

    return coro_wrapped()


async def unwrap_coro_exception(coro):
    try:
        return await coro
    except UserCodeException as uc_exc:
        uc_exc.exc.__suppress_context__ = True
        raise uc_exc.exc


class NestedEventLoops(Exception):
    pass


def clean_traceback(exc: BaseException):
    if os.getenv("SYNCHRONICITY_TRACEBACK", "0") == "1":
        return
    tb = exc.__traceback__

    def should_hide_file(fn: str):
        skip_modules = [synchronicity, concurrent.futures, asyncio]
        res = any(Path(fn).is_relative_to(Path(mod.__file__).parent) for mod in skip_modules)
        return res

    def get_next_valid(tb: TracebackType) -> Optional[TracebackType]:
        while tb is not None and should_hide_file(tb.tb_frame.f_code.co_filename):
            # print("skipping", tb.tb_frame)
            tb = tb.tb_next
        return tb

    cleaned = get_next_valid(tb)
    if cleaned is None:
        # no frames outside of skip_modules - return original error
        return tb
    current = cleaned
    while current.tb_next is not None:
        current.tb_next = get_next_valid(current.tb_next)
        current = current.tb_next

    exc.with_traceback(cleaned)  # side effect
