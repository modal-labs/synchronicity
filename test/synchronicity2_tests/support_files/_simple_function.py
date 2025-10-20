"""Simple async function without any class dependencies."""

import typing

from synchronicity2 import Library

lib = Library("simple_func_lib")


@lib.wrap()
async def simple_add(a: int, b: int) -> int:
    """Add two numbers asynchronously."""
    return a + b


@lib.wrap()
async def simple_generator() -> typing.AsyncGenerator[int, None]:
    """Simple async generator."""
    for i in range(3):
        yield i
