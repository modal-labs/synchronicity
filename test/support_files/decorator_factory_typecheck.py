from typing import assert_type

import decorator_factory

registry = decorator_factory.Registry()


@registry.function()
def f(a: str) -> float:
    return 0.0


assert_type(f.remote("hello"), float)


@registry.function()
async def g(a: str) -> float:
    return 0.0


assert_type(g.remote("hello"), float)
