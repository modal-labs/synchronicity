import typing
from typing import AsyncGenerator, List, TypeVar, Union, overload

from synchronicity.async_wrap import asynccontextmanager


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
        ...

    @classmethod
    def clone(cls, foo: "_Foo") -> "_Foo":  # self ref
        ...


_T = TypeVar("_T", bound=_Foo)


async def _listify(t: _T) -> List[_T]:
    return [t]


@overload
def _overloaded(arg: str) -> float:
    pass


@overload
def _overloaded(arg: int) -> int:
    pass


def _overloaded(arg: Union[str, int]):
    if isinstance(arg, str):
        return float(arg)
    return arg


async def _returns_foo() -> _Foo:
    return _Foo("hello")


@asynccontextmanager
async def make_context(a: float) -> typing.AsyncGenerator[str, None]:
    yield "hello"
