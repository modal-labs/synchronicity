#!/usr/bin/env python3
"""
Command line interface for synchronicity compilation.

Usage:
    python -m synchronicity.cli -m <module> [<module> ...] <synchronizer_name>

The CLI imports the specified modules, which causes them to register wrapped items
with the named synchronizer, then generates wrapper code for all wrapped items.

Examples:
    # Generate wrappers from a single module
    python -m synchronicity.cli -m my.package.module my_sync > generated.py

    # Generate wrappers from multiple modules
    python -m synchronicity.cli -m package.a -m package.b my_sync > generated.py
"""

import argparse
import importlib
import sys
import typing
from pathlib import Path

from synchronicity.codegen.writer import write_modules
from synchronicity.synchronizer import get_synchronizer


def import_module(module_name: str) -> None:
    """
    Import a module to trigger registration of wrapped items.

    Args:
        module_name: Qualified module name (e.g., 'playground.multifile._b')
    """
    try:
        importlib.import_module(module_name)
    except ImportError as e:
        raise ImportError(f"Could not import module '{module_name}': {e}")


def import_modules_two_pass(module_names: list[str]) -> None:
    """
    Import modules in two passes to handle TYPE_CHECKING imports.

    First pass: Normal import to register wrapped items
    Second pass: Reload with TYPE_CHECKING=True to make type annotations available
                 (but prevent re-registration by temporarily disabling wrapping)

    Args:
        module_names: List of qualified module names to import
    """
    import os

    # First pass: Normal imports to register wrapped items
    imported_modules = []
    for module_name in module_names:
        print(f"  Importing module: {module_name}", file=sys.stderr)
        import_module(module_name)
        imported_modules.append(sys.modules[module_name])

    # Second pass: Reload with TYPE_CHECKING=True to resolve all type annotations
    # This allows us to evaluate annotations even if they're in TYPE_CHECKING blocks
    # We temporarily set a flag to prevent re-registration during reload
    original_type_checking = typing.TYPE_CHECKING
    try:
        typing.TYPE_CHECKING = True
        # Set an environment marker to prevent re-registration
        os.environ["_SYNCHRONICITY_SKIP_REGISTRATION"] = "1"
        for module in imported_modules:
            importlib.reload(module)
    finally:
        typing.TYPE_CHECKING = original_type_checking
        if "_SYNCHRONICITY_SKIP_REGISTRATION" in os.environ:
            del os.environ["_SYNCHRONICITY_SKIP_REGISTRATION"]


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Compile synchronicity wrappers for modules using a specific synchronizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate wrappers to files (default)
  python -m synchronicity.cli -m my.package._module my_sync

  # Generate wrappers to a specific directory
  python -m synchronicity.cli -m my.package._module my_sync -o output/

  # Print all modules to stdout
  python -m synchronicity.cli -m my.package._module my_sync --stdout

  # Generate wrappers for multiple modules
  python -m synchronicity.cli -m package._a -m package._b my_sync
        """,
    )
    parser.add_argument(
        "-m",
        "--module",
        action="append",
        dest="modules",
        required=True,
        help="Qualified module name to import (can be specified multiple times)",
    )
    parser.add_argument(
        "synchronizer_name",
        help="Name of the synchronizer to generate wrappers for",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="Output directory for generated files (default: current directory)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print all modules to stdout with file headers instead of writing files",
    )

    args = parser.parse_args()

    synchronizer_name = args.synchronizer_name

    print(f"Importing modules for synchronizer '{synchronizer_name}'...", file=sys.stderr)

    # Import all modules using two-pass loading to handle TYPE_CHECKING imports
    import_modules_two_pass(args.modules)

    # Get the synchronizer and check if it has wrapped items
    synchronizer = get_synchronizer(synchronizer_name)

    if not synchronizer._wrapped:
        print(
            f"\nError: No wrapped items found for synchronizer '{synchronizer_name}' in any of the specified modules",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"\nTotal wrapped items collected: {len(synchronizer._wrapped)}", file=sys.stderr)

    # Compile all wrapped items into separate modules
    from synchronicity.codegen.compile import compile_modules

    print("Compiling wrappers...", file=sys.stderr)
    modules = compile_modules(synchronizer)

    if not modules:
        print("No modules generated", file=sys.stderr)
        sys.exit(1)

    print(f"Generated {len(modules)} module(s)", file=sys.stderr)

    if args.stdout:
        # Print to stdout with file headers
        for module_name in sorted(modules.keys()):
            module_path = module_name.replace(".", "/") + ".py"
            print(f"# File: {module_path}\n")
            print(modules[module_name])
            print()  # Blank line between modules
    else:
        output_dir = Path(args.output_dir)
        for module_path in write_modules(output_dir, modules):
            print(f"  Wrote: {module_path}", file=sys.stderr)
        print("\nCompilation completed successfully!", file=sys.stderr)


if __name__ == "__main__":
    main()
