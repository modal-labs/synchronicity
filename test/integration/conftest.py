"""Pytest configuration for integration tests.

Provides session-scoped fixtures that generate wrapper code once and reuse it across all tests.
"""

import pytest
import shutil
import subprocess
import sys
from pathlib import Path


@pytest.fixture(scope="session")
def generated_wrappers():
    """Generate all wrapper modules once using the CLI and make them available to all tests.

    This fixture:
    1. Uses the synchronicity CLI to generate wrapper code for all support modules
    2. Writes them to generated/ directory in project root
    3. Adds the generated/ directory to sys.path
    4. Returns a namespace with all generated modules
    5. Keeps files after tests complete for manual inspection

    Returns:
        SimpleNamespace with attributes for each generated module
    """
    # Get paths
    project_root = Path(__file__).parent.parent.parent
    support_files_path = Path(__file__).parent.parent / "support_files"
    generated_dir = project_root / "generated"

    # Clean out the generated directory if it exists
    if generated_dir.exists():
        shutil.rmtree(generated_dir)

    # Create fresh generated directory
    generated_dir.mkdir(exist_ok=True)

    # Set up environment with support_files on PYTHONPATH
    import os

    env = os.environ.copy()
    pythonpath_parts = [str(support_files_path), str(project_root)]
    if "PYTHONPATH" in env:
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = ":".join(pythonpath_parts)

    try:
        # Use CLI to generate all wrapper modules
        # List all modules we want to compile
        module_args = []
        module_specs = [
            ("simple_function_impl", "simple_function"),
            ("simple_class_impl", "simple_class"),
            ("class_with_translation_impl", "class_with_translation"),
            ("event_loop_check_impl", "event_loop_check"),
            ("nested_generators_impl", "nested_generators"),
            ("two_way_generator_impl", "two_way_generator"),
            ("multifile_impl._a", "multifile.a"),
            ("multifile_impl._b", "multifile.b"),
        ]

        for module_name, _ in module_specs:
            module_args.extend(["-m", module_name])

        # Run CLI to generate files
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "synchronicity.codegen",
                *module_args,
                "s",  # synchronizer name
                "-o",
                str(generated_dir),
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        if result.returncode != 0:
            print(f"CLI failed: {result.stderr}")
            print(f"CLI stdout: {result.stdout}")
            raise RuntimeError(f"Failed to generate wrapper code: {result.stderr}")

        # Add paths to sys.path:
        # - support_files_path: so generated code can import impl modules (e.g., multifile_impl._a)
        # - generated_dir: so multifile.* can be imported directly
        sys.path.insert(0, str(support_files_path))
        sys.path.insert(0, str(generated_dir))
        yield generated_dir
    finally:
        pass
    # Note: We do NOT delete the generated/ directory - keep files for manual inspection


@pytest.fixture(scope="session")
def support_files():
    return Path(__file__).parent.parent / "support_files"
