"""Integration tests for simple_function_impl.py support file.

Tests execution and type checking of generated code for simple async functions.
"""

from pathlib import Path

from test.integration.test_utils import check_pyright


def test_generated_code_execution_simple(generated_wrappers):
    """Test that generated code can be imported and executed."""
    import simple_function

    # Test the wrapper function
    result = simple_function.simple_add(5, 3)
    assert result == 8, f"Expected 8, got {result}"

    print("✓ Generated code execution test passed")


def test_pyright_simple_function(generated_wrappers):
    """Test that simple function generation passes pyright."""
    import simple_function

    # Verify type correctness with pyright
    check_pyright([Path(simple_function.__file__)])
