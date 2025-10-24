"""Integration tests for end-to-end code generation and execution."""

import inspect
import os
import pytest
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from synchronicity.codegen.compile import compile_modules
from synchronicity.codegen.writer import write_modules


def check_pyright(module_paths: list[Path], extra_pythonpath: Optional[str] = None) -> str:
    """Run pyright on generated code to check for type errors.

    Args:
        code: The generated Python code to check
        module_name: Name for the module file

    Returns:
        True if pyright passes or is not available, False if there are errors
    """
    pythonpath = os.environ.get("PYTHONPATH", "")
    if pythonpath:
        pythonpath += f":{extra_pythonpath}"
    result = subprocess.run(
        ["pyright"] + [str(p) for p in module_paths],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": pythonpath},
    )

    if result.returncode != 0:
        print("  ✗ Pyright validation failed!")
        print(f"    Output: {result.stdout}")
        if result.stderr:
            print(f"    Stderr: {result.stderr}")
        pytest.fail("Pyright validation failed")

    print("  ✓ Pyright validation passed")
    return result.stdout


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


def test_simple_function_generation(tmpdir, monkeypatch):
    """Test generation of simple functions without dependencies."""
    from test.synchronicity2_tests.support_files import _simple_function

    # Generate wrapper code
    modules = compile_modules([_simple_function.wrapper_module], "s")
    assert len(modules) == 1
    module_paths = list(write_modules(Path(tmpdir), modules))
    print(module_paths)
    # Verify that files can be imported
    monkeypatch.syspath_prepend(tmpdir)
    simple_function = __import__("test.synchronicity2_tests.support_files.simple_function")
    assert simple_function.simple_add(2, 4) == 6

    gen = simple_function.simple_generator()
    assert inspect.isgenerator(gen)
    assert list(gen) == [0, 1, 2]
    # Verify type correctness with pyright
    check_pyright(module_paths, tmpdir)

    print("✓ Simple function generation test passed")


def test_simple_class_generation():
    """Test generation of a simple class without translation needs."""
    from test.synchronicity2_tests.support_files import _simple_class

    # Generate wrapper code
    modules = compile_modules(_simple_class.lib)
    generated_code = list(modules.values())[0]  # Extract the single module
    # Verify type correctness with pyright
    check_pyright(generated_code, "simple_class_generated")

    print("✓ Simple class generation test passed")


def test_class_with_translation_generation():
    """Test generation of classes and functions that need type translation."""
    from test.synchronicity2_tests.support_files import _class_with_translation

    # Generate wrapper code
    modules = compile_modules(_class_with_translation.lib)
    generated_code = list(modules.values())[0]  # Extract the single module

    # Verify weakref import
    assert "import weakref" in generated_code

    # Verify _from_impl classmethod generation with class-level cache
    assert (
        "def _from_impl(cls, impl_instance: test.synchronicity2_tests.support_files._class_with_translation.Node)"
        in generated_code
    )
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

    # Verify type correctness with pyright
    check_pyright(generated_code, "class_with_translation_generated")

    print("✓ Class with translation generation test passed")


def test_generated_code_execution_simple():
    """Test that generated code can be imported and executed."""
    from test.synchronicity2_tests.support_files import _simple_function

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
    from test.synchronicity2_tests.support_files import _simple_class

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
    from test.synchronicity2_tests.support_files import _class_with_translation

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
    from test.synchronicity2_tests.support_files import _class_with_translation

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
    from test.synchronicity2_tests.support_files import _class_with_translation

    # Generate wrapper code
    modules = compile_modules(_class_with_translation.lib)
    generated_code = list(modules.values())[0]  # Extract the single module

    # Get paths to support files
    support_dir = Path(__file__).parent / "support_files"
    sync_usage = support_dir / "type_check_usage_sync.py"
    async_usage = support_dir / "type_check_usage_async.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Write the generated module
        wrapper_file = tmppath / "translation_lib.py"
        wrapper_file.write_text(generated_code)

        # Test sync usage
        sync_file = tmppath / "usage_sync.py"
        sync_file.write_text(sync_usage.read_text())

        result_sync = subprocess.run(
            ["pyright", str(sync_file)],
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
            ["pyright", str(async_file)],
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

    # Get path to keyword args test file
    support_dir = Path(__file__).parent / "support_files"
    keyword_usage = support_dir / "type_check_keyword_args.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Write the generated module
        wrapper_file = tmppath / "translation_lib.py"
        wrapper_file.write_text(generated_code)

        # Test keyword arguments
        test_file = tmppath / "usage_keyword.py"
        test_file.write_text(keyword_usage.read_text())

        result = subprocess.run(
            ["pyright", str(test_file)],
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


def test_method_wrapper_aio_execution():
    """Test that calling .aio() on method wrappers works correctly.

    This tests both regular async methods and async generator methods
    to ensure they can be called via .aio() without errors.
    """
    from test.synchronicity2_tests.support_files import _simple_class

    # Generate wrapper code
    modules = compile_modules(_simple_class.lib)
    generated_code = list(modules.values())[0]

    # Execute the generated code to verify it works
    with generated_module(generated_code, "simple_class_generated") as mod:
        import asyncio

        async def test_async_method():
            """Test calling .aio() on a regular async method."""
            counter = mod.Counter(start=10)
            # Call the async version directly
            result = await counter.increment.aio()
            assert result == 11, f"Expected 11, got {result}"
            return result

        async def test_async_generator_method():
            """Test calling .aio() on an async generator method."""
            counter = mod.Counter(start=5)
            # Call the async generator version (get_multiples yields count * i for i in range(n))
            results = []
            async for value in counter.get_multiples.aio(3):
                results.append(value)
            # With count=5 and n=3, should yield 5*0=0, 5*1=5, 5*2=10
            assert results == [0, 5, 10], f"Expected [0, 5, 10], got {results}"
            return results

        # Run the async tests
        result1 = asyncio.run(test_async_method())
        result2 = asyncio.run(test_async_generator_method())

        print(f"✓ Method wrapper .aio() execution: async method returned {result1}")
        print(f"✓ Method wrapper .aio() execution: async generator returned {result2}")


def test_event_loop_execution():
    """Test that all .aio() calls execute in the synchronizer's event loop.

    This is critical - all async code must run in the synchronizer's event loop
    to avoid concurrency issues and ensure proper isolation.
    """
    from test.synchronicity2_tests.support_files import _event_loop_check

    # Generate wrapper code
    modules = compile_modules(_event_loop_check.lib)
    generated_code = list(modules.values())[0]

    # Execute the generated code to verify event loop usage
    with generated_module(generated_code, "event_loop_test_generated") as mod:
        import asyncio

        # Test 1: Function .aio() should run in synchronizer event loop
        async def test_function_aio():
            result = await mod.async_function.aio(5)
            assert result == 10, f"Expected 10, got {result}"
            return result

        # Test 2: Generator function .aio() should run in synchronizer event loop
        async def test_generator_aio():
            results = []
            async for value in mod.async_generator.aio(3):
                results.append(value)
            assert results == [0, 1, 2], f"Expected [0, 1, 2], got {results}"
            return results

        # Test 3: Method .aio() should run in synchronizer event loop
        async def test_method_aio():
            checker = mod.EventLoopChecker(7)
            result = await checker.async_method.aio()
            assert result == 14, f"Expected 14, got {result}"
            return result

        # Test 4: Generator method .aio() should run in synchronizer event loop
        async def test_generator_method_aio():
            checker = mod.EventLoopChecker(3)
            results = []
            async for value in checker.async_generator_method.aio(4):
                results.append(value)
            assert results == [0, 3, 6, 9], f"Expected [0, 3, 6, 9], got {results}"
            return results

        # Run all tests - they will raise AssertionError if not in the right event loop
        result1 = asyncio.run(test_function_aio())
        print(f"✓ Function .aio() runs in synchronizer event loop: {result1}")

        result2 = asyncio.run(test_generator_aio())
        print(f"✓ Generator function .aio() runs in synchronizer event loop: {result2}")

        result3 = asyncio.run(test_method_aio())
        print(f"✓ Method .aio() runs in synchronizer event loop: {result3}")

        result4 = asyncio.run(test_generator_method_aio())
        print(f"✓ Generator method .aio() runs in synchronizer event loop: {result4}")


if __name__ == "__main__":
    test_simple_function_generation()
    test_simple_class_generation()
    test_class_with_translation_generation()
    test_generated_code_execution_simple()
    test_generated_code_execution_class()
    test_generated_code_execution_with_translation()
    test_wrapper_identity_preservation()
    print("\n✅ All code generation integration tests passed!")
