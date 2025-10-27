"""Integration tests for simple_function_impl.py support file.

Tests execution and type checking of generated code for simple async functions.
"""

from pathlib import Path

from synchronicity.codegen.compile import compile_modules
from synchronicity.codegen.writer import write_modules
from test.integration.test_utils import check_pyright


def test_generated_code_execution_simple(generated_wrappers):
    """Test that generated code can be imported and executed."""
    # Test the wrapper function
    result = generated_wrappers.simple_function.simple_add(5, 3)
    assert result == 8, f"Expected 8, got {result}"

    print("✓ Generated code execution test passed")


def test_pyright_simple_function(tmpdir):
    """Test that simple function generation passes pyright."""
    import simple_function_impl

    # Generate wrapper code
    modules = compile_modules([simple_function_impl.wrapper_module], "s")
    module_paths = list(write_modules(Path(tmpdir), modules))

    # Verify type correctness with pyright
    check_pyright(module_paths, str(tmpdir))
