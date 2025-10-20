#!/usr/bin/env python3
"""
Command line interface for synchronicity2 compilation.

Usage:
    python -m synchronicity2.cli -m <module> [<module> ...] <synchronizer_name>

The CLI imports the specified modules, which causes them to register wrapped items
with the named synchronizer, then generates wrapper code for all wrapped items.

Examples:
    # Generate wrappers from a single module
    python -m synchronicity2.cli -m my.package.module my_sync > generated.py

    # Generate wrappers from multiple modules
    python -m synchronicity2.cli -m package.a -m package.b my_sync > generated.py
"""

import argparse
import importlib
import sys

from synchronicity2.synchronizer import get_synchronizer


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

    synchronizer_name = args.synchronizer_name

    print(f"Importing modules for synchronizer '{synchronizer_name}'...", file=sys.stderr)

    # Import all modules - this will cause them to register with the synchronizer
    for module_name in args.modules:
        print(f"  Importing module: {module_name}", file=sys.stderr)
        import_module(module_name)

    # Get the synchronizer and check if it has wrapped items
    synchronizer = get_synchronizer(synchronizer_name)

    if not synchronizer._wrapped:
        print(
            f"\nError: No wrapped items found for synchronizer '{synchronizer_name}' in any of the specified modules",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"\nTotal wrapped items collected: {len(synchronizer._wrapped)}", file=sys.stderr)

    # Compile all wrapped items
    from synchronicity2.compile import compile_library

    print("Compiling wrappers...", file=sys.stderr)
    result = compile_library(synchronizer._wrapped, synchronizer_name)

    print("Compilation completed successfully!", file=sys.stderr)
    print(result)


if __name__ == "__main__":
    main()
