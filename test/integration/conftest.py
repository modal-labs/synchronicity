"""Pytest configuration for integration tests.

Provides session-scoped fixtures that generate wrapper code once and reuse it across all tests.
"""

import pytest
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

from synchronicity.codegen.compile import compile_modules
from synchronicity.codegen.writer import write_modules


@pytest.fixture(scope="session")
def generated_wrappers():
    """Generate all wrapper modules once and make them available to all tests.

    This fixture:
    1. Compiles all support file modules to wrapper code
    2. Writes them to generated/ directory in project root using the writer module
    3. Adds the generated/ directory to sys.path
    4. Returns a namespace with all generated modules
    5. Keeps files after tests complete for manual inspection

    Returns:
        SimpleNamespace with attributes for each generated module
    """
    # Import all support file modules that need wrappers
    from test.support_files import (
        class_with_translation_impl,
        event_loop_check_impl,
        nested_generators_impl,
        simple_class_impl,
        simple_function_impl,
        two_way_generator_impl,
    )

    # Get project root (parent of test directory)
    project_root = Path(__file__).parent.parent.parent
    generated_dir = project_root / "generated"

    # Clean out the generated directory if it exists
    if generated_dir.exists():
        shutil.rmtree(generated_dir)

    # Create fresh generated directory
    generated_dir.mkdir(exist_ok=True)

    try:
        # Compile all modules separately to ensure unique names
        # Scope them under "generated." prefix
        all_modules = {}

        # Compile each module with its own synchronizer name to avoid conflicts
        modules = compile_modules([simple_function_impl.wrapper_module], "test_sync")
        all_modules.update({f"generated.{k}": v for k, v in modules.items()})

        modules = compile_modules([simple_class_impl.wrapper_module], "sync_class")
        all_modules.update({f"generated.{k}": v for k, v in modules.items()})

        modules = compile_modules([class_with_translation_impl.wrapper_module], "sync_trans")
        all_modules.update({f"generated.{k}": v for k, v in modules.items()})

        modules = compile_modules([event_loop_check_impl.wrapper_module], "sync_loop")
        all_modules.update({f"generated.{k}": v for k, v in modules.items()})

        modules = compile_modules([nested_generators_impl.wrapper_module], "sync_nested")
        all_modules.update({f"generated.{k}": v for k, v in modules.items()})

        modules = compile_modules([two_way_generator_impl.wrapper_module], "sync_twoway")
        all_modules.update({f"generated.{k}": v for k, v in modules.items()})

        # Also compile cleanup generator separately for aclose test
        from synchronicity import Module

        cleanup_module = Module("test_aclose")
        cleanup_module.wrap_function(two_way_generator_impl.generator_with_cleanup)
        modules = compile_modules([cleanup_module], "sync_aclose")
        all_modules.update({f"generated.{k}": v for k, v in modules.items()})

        # Write all modules to files using the writer
        # This will create generated/test_support.py, generated/simple_class_lib.py, etc.
        list(write_modules(project_root, all_modules))

        # Add project root to sys.path so we can import generated.*
        sys.path.insert(0, str(project_root))

        # Import all generated modules (use "generated." prefix)
        result = SimpleNamespace()
        result.simple_function = __import__(
            f"generated.{simple_function_impl.wrapper_module.target_module}", fromlist=[""]
        )
        result.simple_class = __import__(f"generated.{simple_class_impl.wrapper_module.target_module}", fromlist=[""])
        result.class_with_translation = __import__(
            f"generated.{class_with_translation_impl.wrapper_module.target_module}", fromlist=[""]
        )
        result.event_loop_check = __import__(
            f"generated.{event_loop_check_impl.wrapper_module.target_module}", fromlist=[""]
        )
        result.nested_generators = __import__(
            f"generated.{nested_generators_impl.wrapper_module.target_module}", fromlist=[""]
        )
        result.two_way_generator = __import__(
            f"generated.{two_way_generator_impl.wrapper_module.target_module}", fromlist=[""]
        )
        result.test_aclose = __import__("generated.test_aclose", fromlist=[""])

        # Store paths for tests that need them
        result.output_dir = generated_dir
        result.generated_code = all_modules  # Keep the generated code strings for verification tests

        yield result

    finally:
        # Clean up: remove from sys.path
        if str(project_root) in sys.path:
            sys.path.remove(str(project_root))

        # Remove imported modules from sys.modules (use actual generated names with prefix)
        modules_to_remove = [
            f"generated.{simple_function_impl.wrapper_module.target_module}",
            f"generated.{simple_class_impl.wrapper_module.target_module}",
            f"generated.{class_with_translation_impl.wrapper_module.target_module}",
            f"generated.{event_loop_check_impl.wrapper_module.target_module}",
            f"generated.{nested_generators_impl.wrapper_module.target_module}",
            f"generated.{two_way_generator_impl.wrapper_module.target_module}",
            "generated.test_aclose",
            "generated",  # Remove the package itself
        ]
        for mod_name in modules_to_remove:
            if mod_name in sys.modules:
                del sys.modules[mod_name]

        # Note: We do NOT delete the generated/ directory - keep files for manual inspection
