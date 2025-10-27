"""Shared utility functions for integration tests."""

import os
import pytest
import subprocess
from pathlib import Path


def check_pyright(module_paths: list[Path], extra_pythonpath: str | None = None) -> str:
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
