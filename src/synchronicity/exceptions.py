import asyncio
import concurrent.futures
import os
import sys
from functools import wraps
from pathlib import Path
from types import TracebackType
from typing import Literal, Optional

import synchronicity

SYNCHRONICITY_TRACEBACK = os.getenv("SYNCHRONICITY_TRACEBACK", "0") == "1"
# note to insert into exception.__notes__ if a traceback frame is hidden
SYNCHRONICITY_TRACEBACK_NOTE = None


class UserCodeException(Exception):
    """This is used to wrap and unwrap exceptions in "user code".

    This lets us have cleaner tracebacks without all the internal synchronicity stuff."""

    def __init__(self, exc):
        # There's always going to be one place inside synchronicity where we
        # catch the exception. We can always safely remove that frame from the
        # traceback.
        self.exc = exc


def wrap_coro_exception(coro):
    @wraps(coro)
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
        except TimeoutError as exc:
            # user-raised TimeoutError always needs to be wrapped, or they would interact
            # with synchronicity's own timeout handling
            # TODO: if we want to get rid of UserCodeException at some point
            #  we could use a custom version of `asyncio.wait_for` to get around this
            raise UserCodeException(exc)
        except Exception as exc:
            if sys.version_info < (3, 11) and not SYNCHRONICITY_TRACEBACK:
                # skip the `await coro` frame from above and any other synchronicity-internal frames
                # (e.g. the coroutine wrappers around asend/athrow/aclose) leading up to user code
                exc.with_traceback(_skip_internal_frames(exc.__traceback__) or exc.__traceback__)
                raise UserCodeException(exc)
            raise  # raise as is on Python 3.11 - we hide things later
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


_skip_modules = [synchronicity, concurrent.futures, asyncio]
_skip_module_roots = [Path(mod.__file__).parent for mod in _skip_modules if mod.__file__]


def _should_hide_file(fn: str) -> bool:
    return any(Path(fn).is_relative_to(modroot) for modroot in _skip_module_roots)


def _skip_internal_frames(tb: Optional[TracebackType]) -> Optional[TracebackType]:
    while tb is not None and _should_hide_file(tb.tb_frame.f_code.co_filename or ""):
        tb = tb.tb_next
    return tb


class suppress_synchronicity_tb_frames:
    def __enter__(self):
        pass

    def __exit__(
        self, exc_type: Optional[type[BaseException]], exc: Optional[BaseException], tb: Optional[TracebackType]
    ) -> Literal[False]:
        if tb is None or exc_type is None or exc is None or SYNCHRONICITY_TRACEBACK:
            # no exception, or enabled full tracebacks - don't do anything
            return False

        cleaned_root = _skip_internal_frames(tb)
        if cleaned_root is None:
            # no frames outside of skip_modules - return original error
            return False

        exc.with_traceback(cleaned_root)  # side effect modification of exception object
        exc_notes = getattr(exc, "__notes__", [])
        if SYNCHRONICITY_TRACEBACK_NOTE is not None and SYNCHRONICITY_TRACEBACK_NOTE not in exc_notes:
            exc_notes.append(exc_notes)

        return False
