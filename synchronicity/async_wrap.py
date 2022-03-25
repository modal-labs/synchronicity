import functools
import inspect

from synchronicity import Interface


def async_compat_wraps(func):
    """Like functools.wraps but maintains `inspect.iscoroutinefunction`

    Use this when the wrapper function is non-async but returns the coroutine resulting
    from calling the underlying wrapped `func`. This will make sure that the wrapper
    is still an async function in that case, and can be inspected as such.

    Note: Does not forward async generator information other than explicit annotations
    """
    if inspect.iscoroutinefunction(func):
        def asyncfunc_deco(user_wrapper):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await user_wrapper(*args, **kwargs)

            return wrapper
        return asyncfunc_deco

    return functools.wraps(func)


def wraps_by_interface(interface, func):
    if interface == Interface.ASYNC:
        return async_compat_wraps(func)
    else:
        return functools.wraps(func)
