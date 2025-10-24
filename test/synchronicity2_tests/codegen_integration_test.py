"""Integration tests for end-to-end code generation and execution."""

import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

# Add src and support_files to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "support_files"))

from synchronicity.codegen.compile import compile_modules


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
    modules = compile_modules(_simple_function.lib)
    generated_code = list(modules.values())[0]  # Extract the single module
    print(generated_code)
    # Verify code structure
    assert "import _simple_function" in generated_code
    assert "class _simple_add:" in generated_code
    assert "class _simple_generator:" in generated_code
    assert "@replace_with(_simple_add_instance)" in generated_code
    assert "@replace_with(_simple_generator_instance)" in generated_code
    assert "def simple_add(a: int, b: int) -> int:" in generated_code
    assert "def simple_generator() -> typing.Generator[int, None, None]:" in generated_code

    # Verify no translation code (no wrapped classes, only simple wrapper classes)
    assert "import weakref" not in generated_code
    assert "_from_impl" not in generated_code
    # Note: _impl_instance is not used in function wrappers, only in class wrappers

    # Code should compile
    compile(generated_code, "<string>", "exec")

    print("✓ Simple function generation test passed")


def test_simple_class_generation():
    """Test generation of a simple class without translation needs."""
    import _simple_class

    # Generate wrapper code
    modules = compile_modules(_simple_class.lib)
    generated_code = list(modules.values())[0]  # Extract the single module

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
    modules = compile_modules(_class_with_translation.lib)
    generated_code = list(modules.values())[0]  # Extract the single module

    # Verify weakref import
    assert "import weakref" in generated_code

    # Verify _from_impl classmethod generation with class-level cache
    assert "def _from_impl(cls, impl_instance: _class_with_translation.Node)" in generated_code
    assert "_instance_cache: weakref.WeakValueDictionary" in generated_code
    assert "if cache_key in cls._instance_cache:" in generated_code
    assert "wrapper = cls.__new__(cls)" in generated_code
    assert "wrapper._impl_instance = impl_instance" in generated_code
    assert "cls._instance_cache[cache_key] = wrapper" in generated_code

    # Verify translation in function signatures (with quoted return types for forward reference safety)
    assert (
        'def create_node(value: int) -> "Node":' in generated_code
        or "def create_node(value: int) -> 'Node':" in generated_code
    )
    assert (
        'def connect_nodes(parent: Node, child: Node) -> "tuple[Node, Node]":' in generated_code
        or "def connect_nodes(parent: Node, child: Node) -> 'tuple[Node, Node]':" in generated_code
    )
    assert (
        'def get_node_list(nodes: list[Node]) -> "list[Node]":' in generated_code
        or "def get_node_list(nodes: list[Node]) -> 'list[Node]':" in generated_code
    )
    assert (
        'def get_optional_node(node: typing.Union[Node, None]) -> "typing.Union[Node, None]":' in generated_code
        or "def get_optional_node(node: typing.Union[Node, None]) -> 'typing.Union[Node, None]':" in generated_code
    )

    # Verify unwrap expressions in function bodies
    assert "parent_impl = parent._impl_instance" in generated_code
    assert "child_impl = child._impl_instance" in generated_code
    assert "[x._impl_instance for x in nodes]" in generated_code

    # Verify wrap expressions in function bodies now use _from_impl
    assert "Node._from_impl(result)" in generated_code
    assert "[Node._from_impl(x) for x in result]" in generated_code

    # Verify method translation (quotes can be single or double)
    assert (
        'def create_child(self, child_value: int) -> "Node":' in generated_code
        or "def create_child(self, child_value: int) -> 'Node':" in generated_code
    )
    assert "return Node._from_impl(result)" in generated_code

    # Code should compile
    compile(generated_code, "<string>", "exec")

    print("✓ Class with translation generation test passed")


def test_generated_code_execution_simple():
    """Test that generated code can be imported and executed."""
    import _simple_function

    # Generate wrapper code
    modules = compile_modules(_simple_function.lib)
    generated_code = list(modules.values())[0]  # Extract the single module

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
    modules = compile_modules(_simple_class.lib)
    generated_code = list(modules.values())[0]  # Extract the single module

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
    modules = compile_modules(_class_with_translation.lib)
    generated_code = list(modules.values())[0]  # Extract the single module

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
    modules = compile_modules(_class_with_translation.lib)
    generated_code = list(modules.values())[0]  # Extract the single module

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
    modules = compile_modules(_class_with_translation.lib)
    generated_code = list(modules.values())[0]  # Extract the single module

    # Check if pyright is available
    venv_pyright = Path(__file__).parent.parent.parent / ".venv" / "bin" / "pyright"
    if not venv_pyright.exists():
        print("✓ Pyright type checking: Skipped (pyright not available)")
        return

    # Get paths to support files
    support_dir = Path(__file__).parent / "support_files"
    sync_usage = support_dir / "type_check_usage_sync.py"
    async_usage = support_dir / "type_check_usage_async.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Write the generated module
        wrapper_file = tmppath / "translation_lib.py"
        wrapper_file.write_text(generated_code)

        # Write a pyright config to disable reportFunctionMemberAccess errors
        pyright_config = tmppath / "pyrightconfig.json"
        pyright_config.write_text('{"reportFunctionMemberAccess": false}')

        # Test sync usage
        sync_file = tmppath / "usage_sync.py"
        sync_file.write_text(sync_usage.read_text())

        result_sync = subprocess.run(
            [str(venv_pyright), str(sync_file)],
            capture_output=True,
            text=True,
            cwd=str(tmppath),
        )

        print(f"Pyright output (sync):\n{result_sync.stdout}")

        if result_sync.returncode != 0:
            print(f"Pyright stderr:\n{result_sync.stderr}")
            assert False, f"Pyright type checking failed for sync usage with exit code {result_sync.returncode}"

        output_sync = result_sync.stdout
        assert 'Type of "create_node" is' in output_sync
        assert 'Type of "connect_nodes" is' in output_sync
        assert 'Type of "create_node.__call__" is' in output_sync
        assert 'Type of "node" is "Node"' in output_sync
        assert 'Type of "child" is "Node"' in output_sync
        assert 'Type of "result" is "tuple[Node, Node]"' in output_sync

        # Test async usage
        async_file = tmppath / "usage_async.py"
        async_file.write_text(async_usage.read_text())

        result_async = subprocess.run(
            [str(venv_pyright), str(async_file)],
            capture_output=True,
            text=True,
            cwd=str(tmppath),
        )

        print(f"Pyright output (async):\n{result_async.stdout}")

        if result_async.returncode != 0:
            print(f"Pyright stderr:\n{result_async.stderr}")
            assert False, f"Pyright type checking failed for async usage with exit code {result_async.returncode}"

        output_async = result_async.stdout
        assert 'Type of "create_node.aio" is "(value: int) -> CoroutineType[Any, Any, Node]"' in output_async
        assert (
            'Type of "connect_nodes.aio" is "(parent: Node, child: Node) -> CoroutineType[Any, Any, tuple[Node, Node]]"'
            in output_async
        )
        assert (
            'Type of "node2.create_child.aio" is "(child_value: int) -> CoroutineType[Any, Any, Node]"' in output_async
        )
        assert 'Type of "node2" is "Node"' in output_async
        assert 'Type of "child2" is "Node"' in output_async
        assert 'Type of "result2" is "tuple[Node, Node]"' in output_async

        print("✓ Pyright type checking: Passed")


def test_pyright_keyword_arguments():
    """Test that keyword arguments work with full signature preservation.

    With the new approach using explicit __call__ signatures, pyright should
    properly infer types for keyword argument calls.
    """
    from test.synchronicity2_tests.support_files import _class_with_translation

    # Generate wrapper code
    modules = compile_modules(_class_with_translation.lib)
    generated_code = list(modules.values())[0]

    # Check if pyright is available
    venv_pyright = Path(__file__).parent.parent.parent / ".venv" / "bin" / "pyright"
    if not venv_pyright.exists():
        print("✓ Keyword argument test: Skipped (pyright not available)")
        return

    # Get path to keyword args test file
    support_dir = Path(__file__).parent / "support_files"
    keyword_usage = support_dir / "type_check_keyword_args.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Write the generated module
        wrapper_file = tmppath / "translation_lib.py"
        wrapper_file.write_text(generated_code)

        # Write a pyright config
        pyright_config = tmppath / "pyrightconfig.json"
        pyright_config.write_text('{"reportFunctionMemberAccess": false}')

        # Test keyword arguments
        test_file = tmppath / "usage_keyword.py"
        test_file.write_text(keyword_usage.read_text())

        result = subprocess.run(
            [str(venv_pyright), str(test_file)],
            capture_output=True,
            text=True,
            cwd=str(tmppath),
        )

        print(f"Pyright output (keyword args):\n{result.stdout}")

        if result.returncode != 0:
            print(f"Pyright stderr:\n{result.stderr}")
            assert False, f"Pyright type checking failed with exit code {result.returncode}"

        # With explicit __call__ signatures, keyword arguments should be properly typed
        assert 'Type of "node1" is "Node"' in result.stdout, "Positional call should work"
        assert 'Type of "node2" is "Node"' in result.stdout, "Keyword call should work"
        assert 'Type of "result" is "tuple[Node, Node]"' in result.stdout, "Keyword call result should be typed"

        print("✓ Keyword arguments: Properly typed with full signature preservation")


if __name__ == "__main__":
    test_simple_function_generation()
    test_simple_class_generation()
    test_class_with_translation_generation()
    test_generated_code_execution_simple()
    test_generated_code_execution_class()
    test_generated_code_execution_with_translation()
    test_wrapper_identity_preservation()
    print("\n✅ All code generation integration tests passed!")
