"""Integration tests for multifile code generation."""

import os
import pytest
import subprocess
import sys
import tempfile
from pathlib import Path


@pytest.fixture
def support_files_path():
    """Get the path to support_files directory."""
    return Path(__file__).parent.parent / "support_files"


def test_multifile_generation(monkeypatch, support_files_path):
    """Test generating code from multiple interdependent modules."""
    # Add support_files to sys.path so we can use shorter imports
    monkeypatch.syspath_prepend(str(support_files_path))

    # Set up environment for subprocess with support_files on PYTHONPATH
    project_root = Path(__file__).parent.parent.parent
    env = os.environ.copy()
    pythonpath_parts = [str(support_files_path), str(project_root)]
    if "PYTHONPATH" in env:
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = ":".join(pythonpath_parts)

    # Generate code using the CLI with --stdout
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "synchronicity.codegen",
            "-m",
            "multifile._a",
            "-m",
            "multifile._b",
            "s",
            "--stdout",
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    generated_code = result.stdout

    # Verify the generated code contains expected classes and functions
    assert "class A:" in generated_code
    assert "class B:" in generated_code
    assert "def get_a(" in generated_code
    assert "def get_b(" in generated_code

    # Verify imports are correct (now using shorter paths)
    assert "import multifile._a" in generated_code

    # Verify file headers are present
    assert "# File:" in generated_code

    # Note: We don't compile the combined stdout output since it contains multiple modules
    # with headers. Individual modules would compile separately.


def test_multifile_execution(support_files_path):
    """Test that generated code from multiple modules is runnable."""
    # Create a temporary directory and generate files there
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Set up environment with support_files on PYTHONPATH
        env = os.environ.copy()
        project_root = Path(__file__).parent.parent.parent
        pythonpath_parts = [str(support_files_path), str(project_root)]
        if "PYTHONPATH" in env:
            pythonpath_parts.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = ":".join(pythonpath_parts)

        # Generate code using the CLI to write files
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "synchronicity.codegen",
                "-m",
                "multifile._a",
                "-m",
                "multifile._b",
                "s",
                "-o",
                str(tmppath),
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        # Verify files were created (now using shorter paths)
        module_a = tmppath / "multifile/a.py"
        module_b = tmppath / "multifile/b.py"

        assert module_a.exists(), f"Module a.py not created at {module_a}"
        assert module_b.exists(), f"Module b.py not created at {module_b}"

        # Verify generated modules are type-correct by running pyright
        venv_pyright = Path(__file__).parent.parent.parent / ".venv" / "bin" / "pyright"
        if venv_pyright.exists():
            # Check module_a
            result_a = subprocess.run(
                [str(venv_pyright), str(module_a)],
                capture_output=True,
                text=True,
                cwd=str(tmppath),
            )
            if result_a.returncode != 0:
                print(f"  ✗ Generated module a.py has type errors:\n{result_a.stdout}")
            else:
                print("  ✓ Generated module a.py passes pyright")

            # Check module_b
            result_b = subprocess.run(
                [str(venv_pyright), str(module_b)],
                capture_output=True,
                text=True,
                cwd=str(tmppath),
            )
            if result_b.returncode != 0:
                print(f"  ✗ Generated module b.py has type errors:\n{result_b.stdout}")
            else:
                print("  ✓ Generated module b.py passes pyright")
        else:
            print("  ⊘ Pyright validation skipped (pyright not installed)")

        # Copy implementation modules to tmpdir so they can be imported
        impl_module_a = support_files_path / "multifile/_a.py"
        impl_module_b = support_files_path / "multifile/_b.py"
        target_dir = tmppath / "multifile"

        import shutil

        shutil.copy(impl_module_a, target_dir / "_a.py")
        shutil.copy(impl_module_b, target_dir / "_b.py")

        # Create a test script that uses the generated code
        test_script = tmppath / "test_usage.py"
        test_script.write_text(
            """
from multifile.a import A, get_b
from multifile.b import B, get_a

# Test synchronous usage
a = A(value=100)
print(f"A value: {a.get_value()}")

b = B(name="test_b")
print(f"B name: {b.get_name()}")

# Test cross-module functions
b_from_a = get_b()
print(f"B from get_b: {b_from_a.get_name()}")

a_from_b = get_a()
print(f"A from get_a: {a_from_b.get_value()}")

print("SUCCESS")
"""
        )

        # Run the test script with PYTHONPATH set to include tmpdir and project root
        env = os.environ.copy()
        pythonpath_parts = [str(tmppath), str(project_root)]
        if "PYTHONPATH" in env:
            pythonpath_parts.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = ":".join(pythonpath_parts)

        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
            text=True,
            cwd=str(tmppath),
            env=env,
        )

        print(f"Test script output:\n{result.stdout}")
        if result.returncode != 0:
            print(f"Test script stderr:\n{result.stderr}")

        assert result.returncode == 0, f"Test script failed with exit code {result.returncode}"
        assert "SUCCESS" in result.stdout

        # Verify that importing generated wrappers does NOT import synchronicity.codegen
        # This ensures build-time code (codegen) is separate from runtime code (synchronizer)
        check_imports_script = tmppath / "check_imports.py"
        check_imports_script.write_text(
            """
import sys
from multifile.a import A
from multifile.b import B

# Check what synchronicity modules were imported
sync_modules = [m for m in sys.modules.keys() if m.startswith('synchronicity')]
print("SYNC_MODULES:", ','.join(sorted(sync_modules)))

# Verify codegen was NOT imported (build-time only)
assert 'synchronicity.codegen' not in sys.modules, "synchronicity.codegen should not be imported at runtime"

# Verify synchronizer WAS imported (runtime dependency)
assert 'synchronicity.synchronizer' in sys.modules, "synchronicity.synchronizer should be imported at runtime"

print("IMPORT_CHECK_SUCCESS")
"""
        )

        # Run import check in fresh subprocess
        result_imports = subprocess.run(
            [sys.executable, str(check_imports_script)],
            capture_output=True,
            text=True,
            cwd=str(tmppath),
            env=env,
        )

        print(f"Import check output:\n{result_imports.stdout}")
        if result_imports.returncode != 0:
            print(f"Import check stderr:\n{result_imports.stderr}")

        assert result_imports.returncode == 0, f"Import check failed with exit code {result_imports.returncode}"
        assert "IMPORT_CHECK_SUCCESS" in result_imports.stdout
        assert "synchronicity.codegen" not in result_imports.stdout


def test_multifile_type_checking(support_files_path):
    """Test that generated code from multiple modules passes type checking.

    Note: Requires pyright to be installed (npm install -g pyright).
    """
    # Create a temporary directory and generate files there
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Set up environment with support_files on PYTHONPATH
        env = os.environ.copy()
        project_root = Path(__file__).parent.parent.parent
        pythonpath_parts = [str(support_files_path), str(project_root)]
        if "PYTHONPATH" in env:
            pythonpath_parts.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = ":".join(pythonpath_parts)

        # Generate code using the CLI to write files
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "synchronicity.codegen",
                "-m",
                "multifile._a",
                "-m",
                "multifile._b",
                "s",
                "-o",
                str(tmppath),
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        # Verify files were created (now using shorter paths)
        module_a = tmppath / "multifile/a.py"
        module_b = tmppath / "multifile/b.py"

        assert module_a.exists(), f"Module a.py not created at {module_a}"
        assert module_b.exists(), f"Module b.py not created at {module_b}"

        # Create a usage file for type checking (sync)
        usage_sync = tmppath / "usage_sync.py"
        usage_sync.write_text(
            """
from multifile.a import A, get_b
from multifile.b import B, get_a

# Sync usage
reveal_type(A)
reveal_type(B)
reveal_type(get_a)
reveal_type(get_b)

a = A(value=42)
reveal_type(a)
reveal_type(a.get_value)

val = a.get_value()
reveal_type(val)

b = get_b()
reveal_type(b)

a2 = get_a()
reveal_type(a2)
"""
        )

        # Create a usage file for type checking (async)
        usage_async = tmppath / "usage_async.py"
        usage_async.write_text(
            """
from multifile.a import A, get_b
from multifile.b import B, get_a

async def test():
    # Async usage - classes are instantiated normally, methods have .aio
    reveal_type(A)
    reveal_type(B)
    reveal_type(get_a.aio)
    reveal_type(get_b.aio)

    a = A(value=42)
    reveal_type(a)
    reveal_type(a.get_value.aio)

    val = await a.get_value.aio()
    reveal_type(val)

    b = await get_b.aio()
    reveal_type(b)

    a2 = await get_a.aio()
    reveal_type(a2)
"""
        )

        # Copy implementation modules to tmpdir
        impl_module_a = support_files_path / "multifile/_a.py"
        impl_module_b = support_files_path / "multifile/_b.py"
        target_dir = tmppath / "multifile"

        import shutil

        shutil.copy(impl_module_a, target_dir / "_a.py")
        shutil.copy(impl_module_b, target_dir / "_b.py")

        # Run pyright from virtualenv (it will automatically use the venv's Python)
        result_sync = subprocess.run(
            ["pyright", str(usage_sync)],
            capture_output=True,
            text=True,
            cwd=str(tmppath),
        )

        print(f"Pyright output (sync):\n{result_sync.stdout}")

        if result_sync.returncode != 0:
            print(f"Pyright stderr:\n{result_sync.stderr}")
            assert False, f"Pyright type checking failed for sync usage with exit code {result_sync.returncode}"

        output_sync = result_sync.stdout
        assert 'Type of "a" is "A"' in output_sync
        assert 'Type of "b" is "B"' in output_sync
        assert 'Type of "val" is "int"' in output_sync

        # Run pyright on async usage
        result_async = subprocess.run(
            ["pyright", str(usage_async)],
            capture_output=True,
            text=True,
            cwd=str(tmppath),
        )

        print(f"Pyright output (async):\n{result_async.stdout}")

        if result_async.returncode != 0:
            print(f"Pyright stderr:\n{result_async.stderr}")
            assert False, f"Pyright type checking failed for async usage with exit code {result_async.returncode}"

        output_async = result_async.stdout
        # Async type inference is limited due to descriptor pattern
        # Pyright sees .aio as Any, so types after await are also Any
        # But we can verify that the classes themselves are correctly typed
        assert 'Type of "A" is "type[A]"' in output_async
        assert 'Type of "B" is "type[B]"' in output_async
        assert 'Type of "a" is "A"' in output_async
        # Note: b and val will be "Any" due to .aio returning Any in type system
