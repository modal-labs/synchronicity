"""Integration tests for end-to-end code generation and execution."""

import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

# Add src and support_files to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "support_files"))

from synchronicity2.compile import compile_library


@contextmanager
def generated_module(code: str, module_name: str):
    """Context manager that writes generated code to a temp file and imports it.

    Args:
        code: The Python code to write
        module_name: Name for the generated module

    Yields:
        The imported module object
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Write the generated module
        wrapper_file = tmppath / f"{module_name}.py"
        wrapper_file.write_text(code)

        # Add to path
        sys.path.insert(0, str(tmppath))

        try:
            # Import the generated module
            module = __import__(module_name)
            yield module
        finally:
            # Clean up
            sys.path.remove(str(tmppath))
            if module_name in sys.modules:
                del sys.modules[module_name]


def test_simple_function_generation():
    """Test generation of simple functions without dependencies."""
    import _simple_function

    # Generate wrapper code
    generated_code = compile_library(_simple_function.lib._wrapped, "simple_func_lib")

    # Verify code structure
    assert "import _simple_function" in generated_code
    assert "class _simple_add:" in generated_code
    assert "class _simple_generator:" in generated_code
    assert "@wrapped_function(_simple_add)" in generated_code
    assert "@wrapped_function(_simple_generator)" in generated_code
    assert "def simple_add(a: int, b: int) -> int:" in generated_code
    assert "def simple_generator() -> typing.Generator[int, None, None]:" in generated_code

    # Verify no translation code (no wrapped classes)
    assert "import weakref" not in generated_code
    assert "_wrap_" not in generated_code
    assert "_impl_instance" not in generated_code

    # Code should compile
    compile(generated_code, "<string>", "exec")

    print("✓ Simple function generation test passed")


def test_simple_class_generation():
    """Test generation of a simple class without translation needs."""
    import _simple_class

    # Generate wrapper code
    generated_code = compile_library(_simple_class.lib._wrapped, "simple_class_lib")

    # Verify code structure
    assert "import _simple_class" in generated_code
    assert "class Counter:" in generated_code
    assert "class Counter_increment:" in generated_code
    assert "class Counter_get_multiples:" in generated_code
    assert "@wrapped_method(Counter_increment)" in generated_code
    assert "@wrapped_method(Counter_get_multiples)" in generated_code
    assert "def __init__(self, start: int = 0):" in generated_code
    assert "_impl_instance = _simple_class.Counter" in generated_code

    # Verify property generation for annotated attribute
    assert "@property" in generated_code
    assert "def count(self) -> int:" in generated_code

    # Code should compile
    compile(generated_code, "<string>", "exec")

    print("✓ Simple class generation test passed")


def test_class_with_translation_generation():
    """Test generation of classes and functions that need type translation."""
    import _class_with_translation

    # Generate wrapper code
    generated_code = compile_library(_class_with_translation.lib._wrapped, "translation_lib")

    # Verify wrapper helper generation
    assert "import weakref" in generated_code
    assert "_cache_Node: weakref.WeakValueDictionary" in generated_code
    assert 'def _wrap_Node(impl_instance: _class_with_translation.Node) -> "Node":' in generated_code
    assert "wrapper = Node.__new__(Node)" in generated_code
    assert "wrapper._impl_instance = impl_instance" in generated_code

    # Verify translation in function signatures
    assert "def create_node(value: int) -> Node:" in generated_code
    assert "def connect_nodes(parent: Node, child: Node) -> tuple[Node, Node]:" in generated_code
    assert "def get_node_list(nodes: list[Node]) -> list[Node]:" in generated_code
    assert "def get_optional_node(node: typing.Union[Node, None]) -> typing.Union[Node, None]:" in generated_code

    # Verify unwrap expressions in function bodies
    assert "parent_impl = parent._impl_instance" in generated_code
    assert "child_impl = child._impl_instance" in generated_code
    assert "[x._impl_instance for x in nodes]" in generated_code

    # Verify wrap expressions in function bodies
    assert "_wrap_Node(result)" in generated_code
    assert "[_wrap_Node(x) for x in result]" in generated_code

    # Verify method translation
    assert "def create_child(self, child_value: int) -> 'Node':" in generated_code
    assert "return _wrap_Node(result)" in generated_code

    # Code should compile
    compile(generated_code, "<string>", "exec")

    print("✓ Class with translation generation test passed")


def test_generated_code_execution_simple():
    """Test that generated code can be imported and executed."""
    import _simple_function

    # Generate wrapper code
    generated_code = compile_library(_simple_function.lib._wrapped, "exec_test_lib")

    # Write to a temporary file and import it
    with generated_module(generated_code, "generated_wrapper") as wrapper:
        # Test the wrapper function
        result = wrapper.simple_add(5, 3)
        assert result == 8, f"Expected 8, got {result}"

        print("✓ Generated code execution test passed")


def test_generated_code_execution_class():
    """Test that generated class wrappers work correctly."""
    import _simple_class

    # Generate wrapper code
    generated_code = compile_library(_simple_class.lib._wrapped, "class_exec_lib")

    # Write to a temporary file and import it
    with generated_module(generated_code, "generated_class_wrapper") as wrapper:
        # Test the wrapper class
        counter = wrapper.Counter(10)
        assert counter.count == 10, f"Expected count=10, got {counter.count}"

        # Test method call
        result = counter.increment()
        assert result == 11, f"Expected 11, got {result}"
        assert counter.count == 11, f"Expected count=11, got {counter.count}"

        # Test generator method
        multiples = list(counter.get_multiples(3))
        assert multiples == [0, 11, 22], f"Expected [0, 11, 22], got {multiples}"

        print("✓ Generated class execution test passed")


def test_generated_code_execution_with_translation():
    """Test that type translation works at runtime."""
    import _class_with_translation

    # Generate wrapper code
    generated_code = compile_library(_class_with_translation.lib._wrapped, "translation_exec_lib")

    # Write to a temporary file and import it
    with generated_module(generated_code, "generated_translation_wrapper") as wrapper:
        # Test node creation
        node = wrapper.create_node(42)
        assert node.value == 42, f"Expected value=42, got {node.value}"

        # Test method that returns same type
        child = node.create_child(100)
        assert child.value == 100, f"Expected value=100, got {child.value}"

        # Verify wrapper caching - creating from same impl should return same wrapper
        assert hasattr(node, "_impl_instance"), "Wrapper should have _impl_instance"
        assert hasattr(child, "_impl_instance"), "Child wrapper should have _impl_instance"

        # Test generator that yields wrapped types
        children = list(node.get_children(3))
        assert len(children) == 3, f"Expected 3 children, got {len(children)}"
        assert children[0].value == 42, f"Expected first child value=42, got {children[0].value}"
        assert children[1].value == 43, f"Expected second child value=43, got {children[1].value}"
        assert children[2].value == 44, f"Expected third child value=44, got {children[2].value}"

        print("✓ Generated code with translation execution test passed")


def test_wrapper_identity_preservation():
    """Test that wrapper identity is preserved through caching."""
    import _class_with_translation

    # Generate wrapper code
    generated_code = compile_library(_class_with_translation.lib._wrapped, "identity_lib")

    # Write to a temporary file and import it
    with generated_module(generated_code, "generated_identity_wrapper") as wrapper:
        # Create a node
        node1 = wrapper.Node(42)

        # Create a child from that node
        child = node1.create_child(100)

        # Pass them through a function that accepts and returns a list
        nodes = wrapper.get_node_list([node1, child])

        # The returned nodes should be the same wrapper instances due to caching
        # (same impl_instance id should return same wrapper)
        assert len(nodes) == 2, f"Expected 2 nodes, got {len(nodes)}"
        assert nodes[0]._impl_instance is node1._impl_instance, "First node impl should be preserved"
        assert nodes[1]._impl_instance is child._impl_instance, "Second node impl should be preserved"

        print("✓ Wrapper identity preservation test passed")


def test_pyright_type_checking():
    """Test that generated code type checks correctly with pyright using reveal_type."""
    import _class_with_translation

    # Generate wrapper code
    generated_code = compile_library(_class_with_translation.lib._wrapped, "translation_lib")

    # Create a usage file with reveal_type to verify types
    usage_code = """from typing import reveal_type
from translation_lib import Node, create_node, connect_nodes

# Test function object types
reveal_type(create_node)  # Should be a callable returning Node
reveal_type(connect_nodes)  # Should be a callable returning tuple[Node, Node]

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
"""

    # Check if pyright is available
    venv_pyright = Path(__file__).parent.parent.parent / ".venv" / "bin" / "pyright"
    if not venv_pyright.exists():
        print("✓ Pyright type checking: Skipped (pyright not available)")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Write the generated module
        wrapper_file = tmppath / "translation_lib.py"
        wrapper_file.write_text(generated_code)

        # Write the usage file
        usage_file = tmppath / "usage.py"
        usage_file.write_text(usage_code)

        # Run pyright
        result = subprocess.run(
            [str(venv_pyright), str(usage_file)],
            capture_output=True,
            text=True,
            cwd=str(tmppath),
        )

        # Print pyright output
        print(f"Pyright output:\n{result.stdout}")

        # Pyright should succeed (exit code 0)
        if result.returncode != 0:
            print(f"Pyright stderr:\n{result.stderr}")
            assert False, f"Pyright type checking failed with exit code {result.returncode}"

        # Verify the revealed types match expectations
        output = result.stdout
        # Function object types
        assert 'Type of "create_node" is' in output, f"Expected create_node type to be revealed, got: {output}"
        assert 'Type of "connect_nodes" is' in output, f"Expected connect_nodes type to be revealed, got: {output}"
        # Return value types
        assert 'Type of "node" is "Node"' in output, f"Expected node type to be Node, got: {output}"
        assert 'Type of "child" is "Node"' in output, f"Expected child type to be Node, got: {output}"
        assert (
            'Type of "result" is "tuple[Node, Node]"' in output
        ), f"Expected result type to be tuple[Node, Node], got: {output}"

        print("✓ Pyright type checking: Passed")


if __name__ == "__main__":
    test_simple_function_generation()
    test_simple_class_generation()
    test_class_with_translation_generation()
    test_generated_code_execution_simple()
    test_generated_code_execution_class()
    test_generated_code_execution_with_translation()
    test_wrapper_identity_preservation()
    print("\n✅ All code generation integration tests passed!")
