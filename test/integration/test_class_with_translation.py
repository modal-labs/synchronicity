"""Integration tests for class_with_translation_impl.py support file.

Tests execution and type checking of generated code for classes requiring type translation.
"""

from pathlib import Path

from test.integration.test_utils import check_pyright


def test_generated_code_execution_with_translation(generated_wrappers):
    """Test that type translation works at runtime."""
    # Create a node
    import class_with_translation

    node = class_with_translation.create_node(42)
    assert node.value == 42, f"Expected node.value=42, got {node.value}"

    # Create a child node
    child = node.create_child(99)
    assert child.value == 99, f"Expected child.value=99, got {child.value}"

    # Connect nodes - this tests that wrapped objects can be passed as arguments
    result_parent, result_child = class_with_translation.connect_nodes(node, child)
    assert result_parent.value == 42, "Expected result_parent.value=42"
    assert result_child.value == 99, "Expected result_child.value=99"

    # Verify identity is preserved through translation
    assert result_parent is node, "Identity should be preserved"
    assert result_child is child, "Identity should be preserved"

    print("✓ Generated code with translation execution test passed")


def test_wrapper_identity_preservation(generated_wrappers):
    """Test that wrapper identity is preserved through translation."""
    # Create a node
    import class_with_translation

    node = class_with_translation.create_node(1)

    # Pass through a function that should preserve identity
    returned_node, _ = class_with_translation.connect_nodes(node, node)

    # Verify identity is preserved when passing through wrapper boundary
    assert returned_node is node, "Wrapper identity should be preserved through function calls"

    print("✓ Wrapper identity preservation test passed")


def test_pyright_class_with_translation(generated_wrappers):
    """Test that class with type translation passes pyright."""
    import class_with_translation_impl

    # Verify type correctness with pyright
    check_pyright([Path(class_with_translation_impl.__file__)])


def test_pyright_type_inference(generated_wrappers, support_files):
    """Test that generated code type checks correctly with pyright using reveal_type."""
    # Get paths to support files
    sync_usage = support_files / "type_check_usage_sync.py"
    async_usage = support_files / "type_check_usage_async.py"

    output_sync = check_pyright([sync_usage])
    print(f"Pyright output (sync):\n{output_sync}")

    assert 'Type of "create_node" is' in output_sync
    assert 'Type of "connect_nodes" is' in output_sync
    assert 'Type of "create_node.__call__" is' in output_sync
    assert 'Type of "node" is "Node"' in output_sync
    assert 'Type of "child" is "Node"' in output_sync
    assert 'Type of "result" is "tuple[Node, Node]"' in output_sync

    # Test async usage
    output_async = check_pyright([async_usage])

    print(f"Pyright output (async):\n{output_async}")

    assert 'Type of "create_node.aio" is "(value: int) -> CoroutineType[Any, Any, Node]"' in output_async
    assert (
        'Type of "connect_nodes.aio" is "(parent: Node, child: Node) -> CoroutineType[Any, Any, tuple[Node, Node]]"'
        in output_async
    )
    assert 'Type of "node2.create_child.aio" is "(child_value: int) -> CoroutineType[Any, Any, Node]"' in output_async
    assert 'Type of "node2" is "Node"' in output_async
    assert 'Type of "child2" is "Node"' in output_async
    assert 'Type of "result2" is "tuple[Node, Node]"' in output_async

    print("✓ Pyright type checking: Passed")


def test_pyright_keyword_arguments(generated_wrappers, support_files):
    """Test that keyword arguments work with full signature preservation.

    With the new approach using explicit __call__ signatures, pyright should
    properly infer types for keyword argument calls.
    """
    # Get path to keyword args test file
    keyword_usage = support_files / "type_check_keyword_args.py"
    stdout = check_pyright([keyword_usage])

    # With explicit __call__ signatures, keyword arguments should be properly typed
    assert 'Type of "node1" is "Node"' in stdout, "Positional call should work"
    assert 'Type of "node2" is "Node"' in stdout, "Keyword call should work"
    assert 'Type of "result" is "tuple[Node, Node]"' in stdout, "Keyword call result should be typed"

    print("✓ Keyword arguments: Properly typed with full signature preservation")
