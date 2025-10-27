"""Integration tests for simple_function_impl.py support file.

Tests execution and type checking of generated code for simple async functions.
"""

from pathlib import Path

from synchronicity.codegen.compile import compile_modules
from synchronicity.codegen.writer import write_modules


def test_generated_code_execution_simple(generated_wrappers):
    """Test that generated code can be imported and executed."""
    # Test the wrapper function
    result = generated_wrappers.simple_function.simple_add(5, 3)
    assert result == 8, f"Expected 8, got {result}"

    print("✓ Generated code execution test passed")


def test_pyright_simple_function(tmpdir):
    """Test that simple function generation passes pyright."""
    import os
    import pytest
    import subprocess

    from test.support_files import simple_function_impl

    def check_pyright(module_paths: list[Path], extra_pythonpath: str = None) -> str:
        """Run pyright on generated code to check for type errors."""
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

    # Generate wrapper code
    modules = compile_modules([simple_function_impl.wrapper_module], "s")
    module_paths = list(write_modules(Path(tmpdir), modules))

    # Verify type correctness with pyright
    check_pyright(module_paths, tmpdir)
