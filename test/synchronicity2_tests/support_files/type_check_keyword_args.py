"""Test that verifies keyword arguments work with the new signature preservation approach.

With the new replace_with decorator pattern and explicit __call__ signatures,
pyright can properly infer parameter names and types, enabling full type
checking for keyword argument calls.
"""

from typing import reveal_type

from translation_lib import Node, connect_nodes, create_node

# Test positional arguments
node1 = create_node(42)
reveal_type(node1)  # Should be Node

# Test keyword arguments - these now work with explicit __call__ signatures!
node2 = create_node(value=100)
reveal_type(node2)  # Should be Node

# Test keyword arguments with multiple params
parent = Node(1)
child = Node(2)

# With explicit __call__ signatures, parameter names are preserved
result = connect_nodes(parent=parent, child=child)
reveal_type(result)  # Should be tuple[Node, Node]
