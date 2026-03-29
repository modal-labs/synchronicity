import typing

import synchronicity

P = typing.ParamSpec("P")
T = typing.TypeVar("T", bound="Node")

mod = synchronicity.Module("callback_translation")


@mod.wrap_class
class Node:
    value: int

    def __init__(self, value: int):
        self.value = value


@mod.wrap_function
async def apply_to_node(node: Node, callback: typing.Callable[[Node], Node]) -> Node:
    return callback(node)


@mod.wrap_function
async def map_node_to_int(node: Node, callback: typing.Callable[[Node], int]) -> int:
    return callback(node)


@mod.wrap_function
def listify(c: typing.Callable[P, T]) -> typing.Callable[P, list[T]]:
    def c2(*args: P.args, **kwargs: P.kwargs):
        return [c(*args, **kwargs)]

    return c2
