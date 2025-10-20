#!/usr/bin/env python3
"""
Command line interface for synchronicity2 compilation.

Usage:
    python -m synchronicity2.cli -m <module> [<module> ...] <synchronizer_name>

The CLI imports the specified modules and collects all Library objects that use the
given synchronizer name, then generates wrapper code for all wrapped items.

Examples:
    # Generate wrappers from a single module
    python -m synchronicity2.cli -m my.package.module my_sync > generated.py

    # Generate wrappers from multiple modules
    python -m synchronicity2.cli -m package.a -m package.b my_sync > generated.py
"""

import argparse
import importlib
import sys
from typing import List

from synchronicity2.synchronizer import Library


def collect_libraries_from_module(module_name: str, synchronizer_name: str) -> List[Library]:
    """
    Import a module and collect all Library objects that match the given synchronizer name.

    Args:
        module_name: Qualified module name (e.g., 'playground.multifile._b')
        synchronizer_name: Name of the synchronizer to filter by

    Returns:
        List of Library objects found in the module with matching synchronizer name
    """
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise ImportError(f"Could not import module '{module_name}': {e}")

    libraries = []
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, Library) and attr._synchronizer_name == synchronizer_name:
            libraries.append(attr)

    return libraries


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Compile synchronicity2 wrappers for modules using a specific synchronizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate wrappers for a single module
  python -m synchronicity2.cli -m my.package.module my_sync

  # Generate wrappers for multiple modules
  python -m synchronicity2.cli -m package.a -m package.b my_sync
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

    args = parser.parse_args()

    # Collect all libraries from all modules
    all_wrapped_items = {}
    synchronizer_name = args.synchronizer_name

    print(f"Collecting wrapped items for synchronizer '{synchronizer_name}'...", file=sys.stderr)

    for module_name in args.modules:
        print(f"  Importing module: {module_name}", file=sys.stderr)
        libraries = collect_libraries_from_module(module_name, synchronizer_name)

        if not libraries:
            print(
                f"  Warning: No Library objects with synchronizer '{synchronizer_name}' found in {module_name}",
                file=sys.stderr,
            )
            continue

        print(f"  Found {len(libraries)} Library object(s)", file=sys.stderr)

        # Merge wrapped items from all libraries
        for library in libraries:
            all_wrapped_items.update(library._wrapped)

    if not all_wrapped_items:
        print(
            f"\nError: No wrapped items found for synchronizer '{synchronizer_name}' in any of the specified modules",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"\nTotal wrapped items collected: {len(all_wrapped_items)}", file=sys.stderr)

    # Compile all wrapped items
    from synchronicity2.compile import compile_library

    print("Compiling wrappers...", file=sys.stderr)
    result = compile_library(all_wrapped_items, synchronizer_name)

    print("Compilation completed successfully!", file=sys.stderr)
    print(result)


if __name__ == "__main__":
    main()
