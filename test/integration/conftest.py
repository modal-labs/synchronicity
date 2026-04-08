"""Pytest configuration for integration tests.

Provides session-scoped fixtures that generate wrapper code once and reuse it across all tests.
"""

import pytest
import shutil
import subprocess
import sys
from pathlib import Path


@pytest.fixture(scope="session", autouse=True)
def generated_wrappers():
    """Generate all wrapper modules once using the CLI and make them available to all tests.

    This fixture:
    1. Vendors ``mylib.synchronicity`` under ``generated/`` and copies ``mylib/_weather_impl.py`` there
    2. Uses the synchronicity CLI to generate wrapper code for all support modules
    3. Runs a second CLI pass for ``mylib.weather`` (synchronizer name from ``Module``)
    4. Adds ``generated/`` and ``support_files`` to ``sys.path``
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

    from synchronicity.codegen.runtime_vendor import vendor_runtime

    vendor_runtime(target_package="mylib.synchronicity", output_base=generated_dir)

    shutil.copy2(
        support_files_path / "mylib" / "_weather_impl.py",
        generated_dir / "mylib" / "_weather_impl.py",
    )

    # Set up environment with support_files on PYTHONPATH
    import os

    env = os.environ.copy()
    pythonpath_parts = [str(support_files_path), str(project_root)]
    if "PYTHONPATH" in env:
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    try:
        # Use CLI to generate all wrapper modules
        # List all modules we want to compile
        module_args = []
        module_specs = [
            "simple_function_impl",
            "simple_class_impl",
            "callback_translation_impl",
            "class_with_translation_impl",
            "class_with_inheritance_impl",
            "class_with_self_references_impl",
            "generic_class_impl",
            "event_loop_check_impl",
            "nested_generators_impl",
            "two_way_generator_impl",
            "functions_with_typevars_impl",
            "multifile_impl._a",
            "multifile_impl._b",
            "classmethod_staticmethod_impl",
            "custom_iterators_impl",
            "multi_synchronizer_impl",
        ]

        for module_name in module_specs:
            module_args.extend(["-m", module_name])

        # Run CLI to generate files
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "synchronicity.codegen",
                "wrappers",
                *module_args,
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

        # README-style mylib package (vendored runtime + mylib.weather wrappers)
        env_weather = os.environ.copy()
        weather_path = [
            str(generated_dir),
            str(support_files_path),
            str(project_root),
        ]
        if "PYTHONPATH" in env_weather:
            weather_path.append(env_weather["PYTHONPATH"])
        env_weather["PYTHONPATH"] = os.pathsep.join(weather_path)
        weather_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "synchronicity.codegen",
                "wrappers",
                "-m",
                "mylib._weather_impl",
                "--runtime-package",
                "mylib.synchronicity",
                "-o",
                str(generated_dir),
            ],
            capture_output=True,
            text=True,
            env=env_weather,
            cwd=str(project_root),
        )
        if weather_result.returncode != 0:
            print(f"Weather CLI failed: {weather_result.stderr}")
            print(f"Weather CLI stdout: {weather_result.stdout}")
            raise RuntimeError(f"Failed to generate mylib.weather: {weather_result.stderr}")

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
