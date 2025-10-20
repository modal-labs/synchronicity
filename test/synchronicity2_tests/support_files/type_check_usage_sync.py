from typing import reveal_type

from translation_lib import Node, connect_nodes, create_node

# Test function object types
reveal_type(create_node)  # Should be a callable returning Node
reveal_type(connect_nodes)  # Should be a callable returning tuple[Node, Node]

# Test __call__ attribute
reveal_type(create_node.__call__)  # Should show callable signature

# Test function return types
node = create_node(42)
reveal_type(node)  # Should be Node

# Test method types
child = node.create_child(100)
reveal_type(child)  # Should be Node

# Test function with multiple args
parent = Node(1)
child_node = Node(2)
result = connect_nodes(parent, child_node)
reveal_type(result)  # Should be tuple[Node, Node]
