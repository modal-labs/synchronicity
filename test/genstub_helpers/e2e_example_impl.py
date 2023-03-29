from typing import AsyncGenerator


class _Foo:
    singleton: "_Foo"
    def __init__(self, arg: str):
        self.arg = arg

    async def getarg(self) -> str:
        return self.arg

    async def gen(self) -> AsyncGenerator[int, None]:
        yield 1

    @staticmethod
    def some_static(arg: str) -> float:
        pass

    @classmethod
    def clone(cls, foo: "_Foo") -> "_Foo":  # self ref
        pass
