"""Pytest configuration for integration tests.

Provides session-scoped fixtures that generate wrapper code once and reuse it across all tests.
"""

import pytest
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


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
        # - project_root: so we can import generated.*
        # - support_files_path: so generated code can import impl modules (e.g., multifile_impl._a)
        # - generated_dir: so multifile.* can be imported directly
        sys.path.insert(0, str(support_files_path))
        sys.path.insert(0, str(generated_dir))

        # Import all generated modules
        result_ns = SimpleNamespace()
        result_ns.simple_function = __import__("simple_function", fromlist=[""])
        result_ns.simple_class = __import__("simple_class", fromlist=[""])
        result_ns.class_with_translation = __import__("class_with_translation", fromlist=[""])
        result_ns.event_loop_check = __import__("event_loop_check", fromlist=[""])
        result_ns.nested_generators = __import__("nested_generators", fromlist=[""])
        result_ns.two_way_generator = __import__("two_way_generator", fromlist=[""])

        # Import multifile modules (can now import via multifile.* or multifile.*)
        result_ns.multifile_a = __import__("multifile.a", fromlist=[""])
        result_ns.multifile_b = __import__("multifile.b", fromlist=[""])

        # For the aclose test, generate a separate module with just that function
        from synchronicity import Module
        from synchronicity.codegen.compile import compile_modules
        from synchronicity.codegen.writer import write_modules
        from test.support_files import two_way_generator_impl

        cleanup_module = Module("test_aclose")
        cleanup_module.wrap_function(two_way_generator_impl.generator_with_cleanup)
        modules = compile_modules([cleanup_module], "sync_aclose")
        aclose_modules = {f"{k}": v for k, v in modules.items()}
        list(write_modules(project_root, aclose_modules))

        result_ns.test_aclose = __import__("test_aclose", fromlist=[""])

        # Store paths for tests that need them
        result_ns.output_dir = generated_dir

        # Store generated code for verification tests
        result_ns.generated_code = {}
        for module_name, target_name in module_specs:
            gen_file = generated_dir / f"{target_name.replace('.', '/')}.py"
            if gen_file.exists():
                result_ns.generated_code[f"{target_name}"] = gen_file.read_text()

        # Add aclose code
        aclose_file = generated_dir / "test_aclose.py"
        if aclose_file.exists():
            result_ns.generated_code["test_aclose"] = aclose_file.read_text()

        yield result_ns
    finally:
        pass
    # Note: We do NOT delete the generated/ directory - keep files for manual inspection
