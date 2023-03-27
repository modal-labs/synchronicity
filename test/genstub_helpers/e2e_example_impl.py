from typing import AsyncGenerator


class _Foo:
    def __init__(self, arg: str):
        self.arg = arg

    async def getarg(self) -> str:
        return self.arg

    async def gen(self) -> AsyncGenerator[int, None]:
        yield 1
