"""Shared utility functions for integration tests."""

import os
import pytest
import re
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


def check_pyright_with_xfail(script_module: str):
    """Pyright checks a file with expected failures
    The expected failures should be documented using comments of the form
    # xfail: <error pattern>
    Where <error pattern> should match the subsequent line's pyright error loosely
    """
    from importlib.util import find_spec

    spec = find_spec(script_module)
    assert spec
    assert spec.has_location
    script_path = spec.origin
    assert script_path
    source = Path(script_path).read_text()
    lines = source.split("\n")
    xfail_starts = [(i, line.lstrip()) for i, line in enumerate(lines) if line.lstrip().startswith("# xfail:")]

    xfail_searches = []
    for line_i, line in xfail_starts:
        current_line = line
        endline_i = line_i

        while current_line.endswith("\\"):  # continuation character
            endline_i += 1
            current_line = lines[endline_i]
            assert current_line.lstrip().startswith("#")  # next line must be a comment

        # skip any lines with comments or empty lines before the offending python lines
        offending_line_i = endline_i
        while current_line.startswith("#") or len(current_line.strip()) == 0:
            offending_line_i += 1
            current_line = lines[offending_line_i]

        chunks = [
            lines[i].lstrip().removeprefix("#").lstrip().removeprefix("xfail:").lstrip().rstrip().removesuffix("\\")
            for i in range(line_i, endline_i + 1)
        ]
        failure_string = " ".join(chunks)

        xfail_searches.append((offending_line_i, failure_string))

    result = subprocess.run(
        ["pyright", script_path],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "")},
    )
    output = result.stdout
    assert f"{len(xfail_searches)} error," in output
    for line_i, error_string in xfail_searches:
        line_no = line_i + 1
        mo = re.search(f"{script_path}:{line_no}:\\d+ - error: ([^\\n]*)", output)
        if not mo:
            pytest.fail(f"expected type failure on line {line_no}, but did not find one")

        actual_error = mo.group(1)
        escaped_pattern = re.escape(error_string)
        reduced_spaces, _ = re.subn(r"(\\\ )+", lambda _: r"\s+", escaped_pattern)
        error_did_match = re.search(reduced_spaces, actual_error, flags=re.S)
        if not error_did_match:
            pytest.fail(f"expected error {error_string!r}, found {actual_error!r}")
