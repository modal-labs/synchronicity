import typing

import synchronicity

P = typing.ParamSpec("P")
T = typing.TypeVar("T", bound="SomeClass")

mod = synchronicity.Module("functions_with_typevars")


@mod.wrap_class
class SomeClass:
    pass


@mod.wrap_class
class Container:
    """A class with methods that use TypeVars."""

    async def tuple_to_list(self, items: tuple[T, ...]) -> list[T]:
        """Wrap any item in a list."""
        return list(items)


@mod.wrap_function
def listify(c: typing.Callable[P, T]) -> typing.Callable[P, list[T]]:
    def c2(*args: P.args, **kwargs: P.kwargs):
        return [c(*args, **kwargs)]

    return c2
