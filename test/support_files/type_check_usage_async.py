from typing import reveal_type

from translation_lib import connect_nodes, create_node

# Test .aio attribute types for functions
reveal_type(create_node.aio)  # Should be async callable returning Node
reveal_type(connect_nodes.aio)  # Should be async callable returning tuple[Node, Node]


async def async_usage() -> None:
    # Test async function return types
    node2 = await create_node.aio(42)
    reveal_type(node2)  # Should be Node

    # Test .aio attribute types for methods
    reveal_type(node2.create_child.aio)  # Should be async callable returning Node

    # Test async method types
    child2 = await node2.create_child.aio(100)
    reveal_type(child2)  # Should be Node

    # Test async function with multiple args
    parent2 = await create_node.aio(1)
    child_node2 = await create_node.aio(2)
    result2 = await connect_nodes.aio(parent2, child_node2)
    reveal_type(result2)  # Should be tuple[Node, Node]
