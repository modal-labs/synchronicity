from typing import assert_type, reveal_type

from generic_class import FunctionWrapper


def f(a: int) -> float: ...


wrapped_func = FunctionWrapper(f)

reveal_type(wrapped_func)
reveal_type(wrapped_func.call)

sync_res = wrapped_func.call(a=10)
assert_type(sync_res, float)


async def foo():
    async_res = await wrapped_func.call.aio(a=10)
    assert_type(async_res, float)
