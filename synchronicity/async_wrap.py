import functools
import inspect
import typing

from .exceptions import UserCodeException
from .interface import Interface


def type_compat_wraps(func, interface: Interface, new_annotations=None):
    """Like functools.wraps but maintains `inspect.iscoroutinefunction` and allows custom type annotations overrides

    Use this when the wrapper function is non-async but returns the coroutine resulting
    from calling the underlying wrapped `func`. This will make sure that the wrapper
    is still an async function in that case, and can be inspected as such.

    Note: Does not forward async generator information other than explicit annotations
    """
    if inspect.iscoroutinefunction(func) and interface == Interface.ASYNC:

        def asyncfunc_deco(user_wrapper):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                try:
                    return await user_wrapper(*args, **kwargs)
                except UserCodeException as uc_exc:
                    raise uc_exc.exc from None
            if new_annotations:
                wrapper.__annotations__ = new_annotations
            return wrapper

        return asyncfunc_deco
    else:
        def blockingfunc_deco(user_wrapper):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return user_wrapper(*args, **kwargs)

            if new_annotations:
                wrapper.__annotations__ = new_annotations

            return wrapper
        return blockingfunc_deco
