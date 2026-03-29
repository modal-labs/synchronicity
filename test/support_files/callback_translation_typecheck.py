from typing import assert_type

from callback_translation import Node, apply_to_node, listify, map_node_to_int


def clone_node(node: Node) -> Node:
    return Node(node.value)


def read_node(node: Node) -> int:
    return node.value


def make_node(x: int) -> Node:
    return Node(x)


node = Node(1)

assert_type(apply_to_node(node, clone_node), Node)
assert_type(map_node_to_int(node, read_node), int)

listified = listify(make_node)
assert_type(listified(3), list[Node])
