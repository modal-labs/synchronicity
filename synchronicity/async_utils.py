import functools
import inspect

from synchronicity import Interface


def async_compat_wraps(func):
    """Like functools.wraps but maintains `inspect.iscoroutinefunction` compatibility

    Use this when the wrapper function is non-async but returns the coroutine resulting
    from calling the underlying wrapped `func`. This will make sure that the wrapper
    is still an async function in that case, and can be inspected as such.
    """
    if inspect.iscoroutinefunction(func):
        return functools.wraps(func)

    def deco(user_wrapper):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await user_wrapper(*args, **kwargs)

        return wrapper
    return deco


def wraps_by_interface(interface, func):
    if interface == Interface.ASYNC:
        return async_compat_wraps(func)
    else:
        return functools.wraps(func)
