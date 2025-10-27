"""Integration tests for multifile code generation.

Tests that multiple interdependent modules can be compiled together and work correctly.
"""

from test.integration.test_utils import check_pyright


def test_multifile_execution(generated_wrappers):
    """Test that generated code from multiple modules is runnable."""
    # Access the pre-generated multifile modules
    from multifile import a as multifile_a, b as multifile_b

    # Test synchronous usage
    a = multifile_a.A(value=100)
    print(f"A value: {a.get_value()}")
    assert a.get_value() == 100

    b = multifile_b.B(name="test_b")
    print(f"B name: {b.get_name()}")
    assert b.get_name() == "test_b"

    # Test cross-module functions
    b_from_a = multifile_a.get_b()
    print(f"B from get_b: {b_from_a.get_name()}")
    assert b_from_a.get_name() == "test"

    a_from_b = multifile_b.get_a()
    print(f"A from get_a: {a_from_b.get_value()}")
    assert a_from_b.get_value() == 42

    print("✓ Multifile execution test passed")


def test_codegen_module_not_imported_at_runtime(generated_wrappers):
    """Test that importing generated wrappers does NOT import synchronicity.codegen.

    This ensures build-time code (codegen) is separate from runtime code (synchronizer).
    """
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create a script to check imports
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

        # Get project root and support files for PYTHONPATH
        project_root = Path(__file__).parent.parent.parent
        support_files = Path(__file__).parent.parent / "support_files"
        generated_dir = project_root / "generated"

        # Set up environment with PYTHONPATH
        import os

        env = os.environ.copy()
        pythonpath_parts = [str(project_root), str(support_files), str(generated_dir)]
        if "PYTHONPATH" in env:
            pythonpath_parts.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = ":".join(pythonpath_parts)

        # Run import check in fresh subprocess
        result_imports = subprocess.run(
            [sys.executable, str(check_imports_script)],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            env=env,
        )

        print(f"Import check output:\n{result_imports.stdout}")
        if result_imports.returncode != 0:
            print(f"Import check stderr:\n{result_imports.stderr}")

        assert result_imports.returncode == 0, f"Import check failed with exit code {result_imports.returncode}"
        assert "IMPORT_CHECK_SUCCESS" in result_imports.stdout
        assert "synchronicity.codegen" not in result_imports.stdout

    print("✓ Import check test passed")


def test_multifile_type_checking(generated_wrappers):
    """Test that generated code from multiple modules passes type checking."""
    from pathlib import Path

    support_files_path = Path(__file__).parent.parent / "support_files"

    usage_sync_src = support_files_path / "multifile_usage_sync.py"
    usage_async_src = support_files_path / "multifile_usage_async.py"

    result_sync = check_pyright([usage_sync_src])
    print(f"Pyright output (sync):\n{result_sync}")

    output_sync = result_sync
    assert 'Type of "a" is "A"' in output_sync
    assert 'Type of "b" is "B"' in output_sync
    assert 'Type of "val" is "int"' in output_sync

    # Run pyright on async usage
    result_sync = check_pyright([usage_async_src])
    print(f"Pyright output (async):\n{result_sync}")
    output_async = result_sync
    # Async type inference is limited due to descriptor pattern
    # Pyright sees .aio as Any, so types after await are also Any
    # But we can verify that the classes themselves are correctly typed
    assert 'Type of "A" is "type[A]"' in output_async
    assert 'Type of "B" is "type[B]"' in output_async
    assert 'Type of "a" is "A"' in output_async

    print("✓ Type checking test passed")


def test_multifile_generated_modules(generated_wrappers):
    """Test that multifile modules are correctly generated using pyright."""
    from pathlib import Path

    # Get generated multifile module paths
    generated_dir = generated_wrappers
    module_a: Path = generated_dir / "multifile/a.py"
    module_b: Path = generated_dir / "multifile/b.py"

    assert module_a.exists(), f"Module a.py not found at {module_a}"
    assert module_b.exists(), f"Module b.py not found at {module_b}"

    # Verify the generated modules pass pyright
    # Need both project root and support_files in PYTHONPATH
    project_root = generated_dir.parent
    support_files = Path(__file__).parent.parent / "support_files"
    pythonpath = f"{project_root}:{support_files}"
    check_pyright([module_a, module_b], pythonpath)

    module_a_src = module_a.read_text()
    module_b_src = module_b.read_text()
    # Verify generated code contains expected classes and functions
    assert "class A:" in module_a_src
    assert "class B:" in module_b_src
    assert "class A" not in module_b_src
    assert "class B" not in module_a_src
    assert "def get_b(" in module_a_src
    assert "def get_a(" in module_b_src

    print("✓ Generated modules test passed")
