"""Simple async function without any class dependencies."""

import typing

from synchronicity import Module

wrapper_module = Module("simple_function")


@wrapper_module.wrap_function
async def simple_add(a: int, b: int) -> int:
    """Add two numbers asynchronously."""
    return a + b


@wrapper_module.wrap_class
async def simple_generator() -> typing.AsyncGenerator[int, None]:
    """Simple async generator."""
    for i in range(3):
        yield i
