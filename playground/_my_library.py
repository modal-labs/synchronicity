import typing

from synchronicity import Module

lib = Module("my_library")


@lib.wrap_function
async def foo() -> typing.AsyncGenerator[int, None]:
    yield 1


@lib.wrap_class
class Bar:
    a: str

    def __init__(self, a: str):
        self.a = a

    async def moo(self, s: str) -> typing.AsyncGenerator[str, None]:
        for c1, c2 in zip(self.a, s):
            yield f"{c1}{c2}"

    def sync_func(self, b: "Bar") -> "Bar":
        return b


@lib.wrap_function
async def accepts_bar(b: Bar) -> Bar:
    assert isinstance(b, Bar)
    return b


@lib.wrap_class
def accepts_bar_sync(b: Bar) -> Bar:
    assert isinstance(b, Bar)
    return b


@lib.wrap_function
async def nested_async_generator(i: int) -> tuple[typing.AsyncGenerator[str]]:
    async def f():
        for _ in range(i):
            yield "hello"

    async def g():
        for _ in range(i):
            yield "world"

    return (f(), g())
