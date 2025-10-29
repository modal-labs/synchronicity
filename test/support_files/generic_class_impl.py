from typing import Callable, Generic, ParamSpec, TypeVar

import synchronicity

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T", bound="Container")

mod = synchronicity.Module("generic_class")


@mod.wrap_class
class Container(Generic[T]):
    """A generic container class."""

    def __init__(self, value: T):
        self.value = value

    async def get(self) -> T:
        return self.value

    async def set(self, value: T) -> None:
        self.value = value


@mod.wrap_class
class FunctionWrapper(Generic[P, R]):
    """A wrapper around a callable."""

    def __init__(self, f: Callable[P, R]):
        self.f = f

    async def call(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return self.f(*args, **kwargs)
