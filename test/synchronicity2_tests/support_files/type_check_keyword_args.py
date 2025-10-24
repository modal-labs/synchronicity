"""Test that demonstrates the ParamSpec limitation with keyword arguments.

With the current AioWrapper[[T1, T2], R] approach, pyright cannot infer
parameter names, only types. This means keyword argument calls are not
properly type-checked.
"""

from typing import reveal_type

from translation_lib import Node, connect_nodes, create_node

# Test positional arguments (these work)
node1 = create_node(42)
reveal_type(node1)  # Should be Node

# Test keyword arguments - THIS IS THE PROBLEM
# With explicit [[int], Node], pyright doesn't know the parameter is named "value"
node2 = create_node(value=100)  # Pyright should accept this
reveal_type(node2)  # Should be Node, but might be Unknown/Any

# Test keyword arguments with multiple params
parent = Node(1)
child = Node(2)

# With explicit [[Node, Node], tuple[Node, Node]], pyright doesn't know
# the parameter names are "parent" and "child"
result = connect_nodes(parent=parent, child=child)
reveal_type(result)  # Should be tuple[Node, Node], but might be Unknown/Any
