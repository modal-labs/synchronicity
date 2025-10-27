"""Integration tests for type checking generated code.

Tests that generated code passes Pyright type checking and that
type annotations are preserved correctly.
"""

import os
import pytest
import subprocess
import tempfile
from pathlib import Path

from synchronicity.codegen.compile import compile_modules


def check_pyright(module_paths: list[Path], extra_pythonpath: str = None) -> str:
    """Run pyright on generated code to check for type errors.

    Args:
        module_paths: List of module file paths to check
        extra_pythonpath: Additional path to add to PYTHONPATH

    Returns:
        Pyright output if successful

    Raises:
        pytest.fail if pyright fails
    """
    pythonpath = os.environ.get("PYTHONPATH", "")
    if extra_pythonpath:
        if pythonpath:
            pythonpath += f":{extra_pythonpath}"
        else:
            pythonpath = extra_pythonpath

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


def test_pyright_simple_function(tmpdir):
    """Test that simple function generation passes pyright."""
    from synchronicity.codegen.writer import write_modules
    from test.support_files import simple_function_impl

    # Generate wrapper code
    modules = compile_modules([simple_function_impl.wrapper_module], "s")
    module_paths = list(write_modules(Path(tmpdir), modules))

    # Verify type correctness with pyright
    check_pyright(module_paths, tmpdir)


def test_pyright_simple_class(tmpdir):
    """Test that simple class generation passes pyright."""
    from synchronicity.codegen.writer import write_modules
    from test.support_files import simple_class_impl

    # Generate wrapper code
    modules = compile_modules([simple_class_impl.wrapper_module], "s")
    module_paths = list(write_modules(Path(tmpdir), modules))

    # Verify type correctness with pyright
    check_pyright(module_paths, tmpdir)


def test_pyright_class_with_translation(tmpdir):
    """Test that class with type translation passes pyright."""
    from synchronicity.codegen.writer import write_modules
    from test.support_files import class_with_translation_impl

    # Generate wrapper code
    modules = compile_modules([class_with_translation_impl.wrapper_module], "s")
    module_paths = list(write_modules(Path(tmpdir), modules))

    # Verify type correctness with pyright
    check_pyright(module_paths, tmpdir)


def test_pyright_type_inference():
    """Test that generated code type checks correctly with pyright using reveal_type."""
    from test.support_files import class_with_translation_impl

    # Generate wrapper code
    modules = compile_modules([class_with_translation_impl.wrapper_module], "s")
    generated_code = list(modules.values())[0]  # Extract the single module

    # Get paths to support files
    support_dir = Path(__file__).parent.parent / "support_files"
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
    from test.support_files import class_with_translation_impl

    # Generate wrapper code
    modules = compile_modules([class_with_translation_impl.wrapper_module], "s")
    generated_code = list(modules.values())[0]

    # Get path to keyword args test file
    support_dir = Path(__file__).parent.parent / "support_files"
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
