import typing
from typing import Awaitable, Callable

from synchronicity2.synchronizer import Synchronizer

P = typing.ParamSpec("P")
R = typing.TypeVar("R")


class GenericFunctionWrapper(typing.Generic[P, R]):
    """This could be used to wrap any function, but will not translate any types
    and will add a layer of indirection that makes code navigation hard"""

    synchronizer: Synchronizer
    impl_function: Callable[P, Awaitable[R]]

    def __init__(self, impl_function: Callable[P, Awaitable[R]], synchronizer: Synchronizer):
        self.impl_function = impl_function
        self.synchronizer = synchronizer

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return self.synchronizer._run_function_sync(self.impl_function(*args, **kwargs))

    async def aio(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return await self.synchronizer._run_function_async(self.impl_function(*args, **kwargs))


# Template for function wrappers - not meant to be executed directly
# class _FunctionWrapperTemplate:  # replace with specific name
#     synchronizer = get_synchronizer("my_library")
#     impl_function = library_mod.library_func  # replace with reference to original function
#
#     def __call__(self, *args, **kwargs):
#         coro = self.impl_function(*args, **kwargs)
#         raw_result = self.synchronizer._run_function_sync(coro)
#         return raw_result
#
#     async def aio(self, *args, **kwargs):
#         coro = self.impl_function(*args, **kwargs)
#         raw_result = await self.synchronizer._run_function_async(coro)
#         return raw_result
#
# function_wrapper = _FunctionWrapperTemplate()
