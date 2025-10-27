#!/usr/bin/env python3
"""
Command line interface for synchronicity compilation.

Usage:
    python -m synchronicity.codegen -m <module> [<module> ...] <synchronizer_name>
    # Or use the CLI entrypoint:
    synchronicity -m <module> [<module> ...] <synchronizer_name>

The CLI imports the specified modules, which causes them to register wrapped items
with the named synchronizer, then generates wrapper code for all wrapped items.

Examples:
    # Generate wrappers from a single module
    python -m synchronicity.codegen -m my.package.module my_sync > generated.py
    synchronicity -m my.package.module my_sync > generated.py

    # Generate wrappers from multiple modules
    python -m synchronicity.codegen -m package.a -m package.b my_sync > generated.py
    synchronicity -m package.a -m package.b my_sync > generated.py
"""

import argparse
import importlib
import sys
import typing
from pathlib import Path

from .writer import write_modules


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


def import_modules_two_pass(module_names: list[str]) -> list:
    """
    Import modules in two passes to handle TYPE_CHECKING imports.

    First pass: Normal import to register wrapped items
    Second pass: Reload with TYPE_CHECKING=True to make type annotations available

    Args:
        module_names: List of qualified module names to import

    Returns:
        List of imported module objects
    """

    # First pass: Normal imports to register wrapped items
    imported_modules = []
    for module_name in module_names:
        print(f"  Importing module: {module_name}", file=sys.stderr)
        import_module(module_name)
        imported_modules.append(sys.modules[module_name])

    # Second pass: Reload with TYPE_CHECKING=True to resolve all type annotations
    # This allows us to evaluate annotations even if they're in TYPE_CHECKING blocks
    # Classes/functions will register again with their reloaded identities, which is fine
    # since they map to the same target modules/names
    original_type_checking = typing.TYPE_CHECKING
    try:
        typing.TYPE_CHECKING = True
        for module in imported_modules:
            importlib.reload(module)
    finally:
        typing.TYPE_CHECKING = original_type_checking

    return imported_modules


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Compile synchronicity wrappers for modules using a specific synchronizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate wrappers to files (default)
  python -m synchronicity.codegen -m my.package._module my_sync
  synchronicity -m my.package._module my_sync

  # Generate wrappers to a specific directory
  python -m synchronicity.codegen -m my.package._module my_sync -o output/
  synchronicity -m my.package._module my_sync -o output/

  # Print all modules to stdout
  python -m synchronicity.codegen -m my.package._module my_sync --stdout
  synchronicity -m my.package._module my_sync --stdout

  # Generate wrappers for multiple modules
  python -m synchronicity.codegen -m package._a -m package._b my_sync
  synchronicity -m package._a -m package._b my_sync
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

    # Import modules and collect Module objects

    from synchronicity.module import Module

    from .compile import compile_modules

    # First pass: Normal imports to register wrapped items
    for module_name in args.modules:
        print(f"  Importing module: {module_name}", file=sys.stderr)
        importlib.import_module(module_name)

    # Second pass: Reload with TYPE_CHECKING=True to resolve forward references
    # This creates new Module instances with reloaded class objects that have
    # fully-evaluatable type annotations
    original_type_checking = typing.TYPE_CHECKING
    try:
        typing.TYPE_CHECKING = True
        for module_name in args.modules:
            importlib.reload(sys.modules[module_name])
    finally:
        typing.TYPE_CHECKING = original_type_checking

    # Collect Module objects after reload (so they have the correct class objects)
    module_objects = []
    for module_name in args.modules:
        imported_module = sys.modules[module_name]
        for attr_name in dir(imported_module):
            attr = getattr(imported_module, attr_name)
            if isinstance(attr, Module):
                module_objects.append(attr)
                print(f"  Found Module: {attr.target_module} with {len(attr.module_items())} items", file=sys.stderr)

    if not module_objects:
        print(
            "\nError: No Module objects found in the specified modules.",
            file=sys.stderr,
        )
        print(
            "Make sure you have created a Module instance and decorated your functions/classes with it:",
            file=sys.stderr,
        )
        print("  wrapper_module = Module('my_module')", file=sys.stderr)
        print("  @wrapper_module.wrap_function", file=sys.stderr)
        sys.exit(1)

    # Count total registered items
    total_items = sum(len(m.module_items()) for m in module_objects)
    print(f"\nTotal registered items: {total_items}", file=sys.stderr)

    print("Compiling wrappers...", file=sys.stderr)

    # Compile using the Module-based API
    modules = compile_modules(module_objects, synchronizer_name)

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
