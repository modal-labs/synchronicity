import typing

from synchronicity2 import Library

lib = Library("my_library")


@lib.wrap()
async def foo() -> typing.AsyncGenerator[int, None]:
    yield 1


@lib.wrap()
class Bar:
    a: str

    def __init__(self, a: str):
        self.a = a

    async def moo(self, s: str) -> typing.AsyncGenerator[str, None]:
        for c1, c2 in zip(self.a, s):
            yield f"{c1}{c2}"


@lib.wrap()
def accepts_bar(b: Bar) -> Bar:
    assert isinstance(b, Bar)
    return b
