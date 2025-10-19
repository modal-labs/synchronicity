import typing

from synchronicity2 import Library

lib = Library("my_library")


@lib.wrap()
async def foo() -> typing.AsyncGenerator[int, None]:
    yield 1


@lib.wrap()
class Bar:
    a: str = "hello"

    async def moo(s: str) -> typing.AsyncGenerator[bool, None]:
        yield False
