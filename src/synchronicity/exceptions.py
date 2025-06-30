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
        except TimeoutError as exc:
            # user-raised TimeoutError always needs to be wrapped, or they would interact
            # with synchronicity's own timeout handling
            # TODO: if we want to get rid of UserCodeException at some point
            #  we could use a custom version of `asyncio.wait_for` to get around this
            raise UserCodeException(exc)
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


_skip_modules = [synchronicity, concurrent.futures, asyncio]
_skip_module_roots = [Path(mod.__file__).parent for mod in _skip_modules if mod.__file__]


def suppress_synchronicity_tb_frames(exc: BaseException):
    if os.getenv("SYNCHRONICITY_TRACEBACK", "0") == "1":
        return
    tb = exc.__traceback__
    if tb is None:
        return

    def should_hide_file(fn: str):
        return any(Path(fn).is_relative_to(modroot) for modroot in _skip_module_roots)

    skipped_frames_collection = []

    def get_next_valid(tb: TracebackType) -> Optional[TracebackType]:
        skipped_frames = 0
        next_valid: Optional[TracebackType] = tb
        while next_valid is not None and should_hide_file(next_valid.tb_frame.f_code.co_filename or ""):
            next_valid = next_valid.tb_next
            skipped_frames += 1
        skipped_frames_collection.append(skipped_frames)
        return next_valid

    cleaned_root = get_next_valid(tb)
    if cleaned_root is None:
        # no frames outside of skip_modules - return original error
        return tb

    return exc.with_traceback(cleaned_root)  # side effect


class suppress_tb_frames:
    """Utility context manager which can be used to suppress individual traceback frames

    E.g.
    This hides the `raise Exception("foo")` line itself from the traceback:

    ```py
    with supress_tb_frames(1):
        raise Exception("foo")
    ```

    Only works on Python 3.11+ where `exc.with_traceback()` actually has effect on
    what's printed by the global traceback printer.
    """

    def __init__(self, n: int):
        self.n = n

    def __enter__(self):
        pass

    def __exit__(
        self, exc_type: Optional[type[BaseException]], exc: Optional[BaseException], tb: Optional[TracebackType]
    ) -> bool:
        if exc_type is None:
            # no exception - don't do anything
            return False

        final_tb = tb
        if os.getenv("SYNCHRONICITY_TRACEBACK", "0") != "1":
            try:
                for _ in range(self.n):
                    final_tb = final_tb.tb_next
            except AttributeError:
                return False  # tried to remove too many frames - unexpected, so just return the full traceback
            # modify traceback on exception object
            exc.with_traceback(final_tb)
        return False
