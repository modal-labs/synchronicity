import collections.abc
import contextlib
import functools
import inspect
import typing
from contextlib import asynccontextmanager as _asynccontextmanager
from types import TracebackType
from typing import Optional

import typing_extensions

from .exceptions import UserCodeException, clean_traceback
from .interface import Interface


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
            return False

        # modify traceback on exception object
        try:
            final_tb = tb
            for _ in range(self.n):
                final_tb = final_tb.tb_next
        except AttributeError:
            return False  # tried to remove too many frames - unexpected, so just return the full traceback

        exc.with_traceback(final_tb)
        return False


def wraps_by_interface(interface: Interface, func):
    """Like functools.wraps but maintains `inspect.iscoroutinefunction` and allows custom type annotations overrides

    Use this when the wrapper function is non-async but returns the coroutine resulting
    from calling the underlying wrapped `func`. This will make sure that the wrapper
    is still an async function in that case, and can be inspected as such.

    Note: Does not forward async generator information other than explicit annotations
    """
    if is_coroutine_function_follow_wrapped(func) and interface == Interface._ASYNC_WITH_BLOCKING_TYPES:

        def asyncfunc_deco(user_wrapper):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                try:
                    return await user_wrapper(*args, **kwargs)
                except UserCodeException as uc_exc:
                    uc_exc.exc.__suppress_context__ = True
                    raise uc_exc.exc
                except Exception as exc:
                    clean_traceback(exc)
                    raise

            return wrapper

        return asyncfunc_deco
    else:
        return functools.wraps(func)


def is_coroutine_function_follow_wrapped(func: typing.Callable) -> bool:
    """Determine if func returns a coroutine, unwrapping decorators, but not the async synchronicity interace."""
    from .synchronizer import TARGET_INTERFACE_ATTR  # Avoid circular import

    if hasattr(func, "__wrapped__") and getattr(func, TARGET_INTERFACE_ATTR, None) != Interface.BLOCKING:
        return is_coroutine_function_follow_wrapped(func.__wrapped__)
    return inspect.iscoroutinefunction(func)


def is_async_gen_function_follow_wrapped(func: typing.Callable) -> bool:
    """Determine if func returns an async generator, unwrapping decorators, but not the async synchronicity interace."""
    from .synchronizer import TARGET_INTERFACE_ATTR  # Avoid circular import

    if hasattr(func, "__wrapped__") and getattr(func, TARGET_INTERFACE_ATTR, None) != Interface.BLOCKING:
        return is_async_gen_function_follow_wrapped(func.__wrapped__)
    return inspect.isasyncgenfunction(func)


YIELD_TYPE = typing.TypeVar("YIELD_TYPE")
SEND_TYPE = typing.TypeVar("SEND_TYPE")


P = typing_extensions.ParamSpec("P")


def asynccontextmanager(
    f: typing.Callable[P, typing.AsyncGenerator[YIELD_TYPE, SEND_TYPE]],
) -> typing.Callable[P, typing.AsyncContextManager[YIELD_TYPE]]:
    """Wrapper around contextlib.asynccontextmanager that sets correct type annotations

    The standard library one doesn't
    """
    acm_factory: typing.Callable[..., typing.AsyncContextManager[YIELD_TYPE]] = _asynccontextmanager(f)

    old_ret = acm_factory.__annotations__.pop("return", None)
    if old_ret is not None:
        if old_ret.__origin__ in [
            collections.abc.AsyncGenerator,
            collections.abc.AsyncIterator,
            collections.abc.AsyncIterable,
        ]:
            acm_factory.__annotations__["return"] = typing.AsyncContextManager[old_ret.__args__[0]]  # type: ignore
        elif old_ret.__origin__ == contextlib.AbstractAsyncContextManager:
            # if the standard lib fixes the annotations in the future, lets not break it...
            return acm_factory
    else:
        raise ValueError(
            "To use the fixed @asynccontextmanager, make sure to properly"
            " annotate your wrapped function as an AsyncGenerator"
        )

    return acm_factory
