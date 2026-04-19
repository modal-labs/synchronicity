#!/usr/bin/env python3
"""
Command line interface for synchronicity compilation and runtime vendoring.

Usage:
    synchronicity wrappers -m <module> [<module> ...] [-o DIR] ...
    synchronicity vendor <dotted.package.path> -o <output_dir>

    python -m synchronicity.codegen wrappers -m <module> ...

The ``wrappers`` command imports the specified modules, which causes them to register
wrapped items with ``Module`` (including each module's synchronizer name), then
generates wrapper code.
"""

from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
import tempfile
import typing
from pathlib import Path

from .writer import write_modules


def run_ruff_on_file(file_path: Path) -> None:
    """
    Run ruff check --fix and ruff format on a single file.

    Args:
        file_path: Path to the file to format
    """
    # Run ruff check --fix for autofixes
    subprocess.run(
        ["ruff", "check", "--fix", str(file_path)],
        capture_output=True,
        text=True,
    )

    # Run ruff format
    subprocess.run(
        ["ruff", "format", str(file_path)],
        capture_output=True,
        text=True,
    )


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synchronicity",
        description="Vendor the synchronicity runtime and generate sync/async wrapper modules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    vendor_parser = subparsers.add_parser(
        "vendor",
        help="Copy runtime (Module, synchronizer, types, descriptor) into a package tree",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  synchronicity vendor my_lib.synchronicity -o src/

Creates src/my_lib/synchronicity/{__init__.py,module.py,types.py,descriptor.py,synchronizer.py}.
Then pass --runtime-package my_lib.synchronicity to ``synchronicity wrappers`` so generated
code imports that package instead of top-level synchronicity.
        """,
    )
    vendor_parser.add_argument(
        "target_package",
        help="Dotted package path to create under the output directory (e.g. my_lib.synchronicity)",
    )
    vendor_parser.add_argument(
        "-o",
        "--output-dir",
        required=True,
        type=Path,
        help="Base directory; package directories are created beneath it",
    )

    wrappers_parser = subparsers.add_parser(
        "wrappers",
        help="Generate wrapper modules from implementation modules using Module registration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  synchronicity wrappers -m my.package._module
  synchronicity wrappers -m my.package._module -o output/
  synchronicity wrappers -m my.package._module --ruff
  synchronicity wrappers -m my.package._module --stdout
  synchronicity wrappers -m package._a -m package._b
  synchronicity vendor mylib.synchronicity -o src/
  synchronicity wrappers -m mylib._impl --runtime-package mylib.synchronicity -o src/

  python -m synchronicity.codegen wrappers -m my.package._module
        """,
    )
    wrappers_parser.add_argument(
        "-m",
        "--module",
        action="append",
        dest="modules",
        required=True,
        help="Qualified module name to import (can be specified multiple times)",
    )
    wrappers_parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="Output directory for generated files (default: current directory)",
    )
    wrappers_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print all modules to stdout with file headers instead of writing files",
    )
    wrappers_parser.add_argument(
        "--ruff",
        action="store_true",
        help="Run ruff to autofix and format the generated files (works with both file output and --stdout)",
    )
    wrappers_parser.add_argument(
        "--runtime-package",
        default="synchronicity",
        metavar="DOTTED.PATH",
        help=(
            "Dotted import path for synchronicity runtime in generated code (default: synchronicity). "
            "Set to your vendored package (see `synchronicity vendor`) for self-contained wheels."
        ),
    )

    return parser


def _run_vendor(args: argparse.Namespace) -> None:
    from .runtime_vendor import vendor_runtime

    try:
        dest = vendor_runtime(target_package=args.target_package, output_base=args.output_dir.resolve())
    except (ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Vendored runtime to {dest}", file=sys.stderr)


def _run_wrappers(args: argparse.Namespace) -> None:
    from .compile import compile_modules
    from .runtime_vendor import validate_runtime_package

    try:
        validate_runtime_package(args.runtime_package)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    # Use the same ``Module`` class as implementation code: vendored copies are a
    # distinct type from ``synchronicity.module.Module``, so ``isinstance`` must use
    # the class from ``--runtime-package`` (default ``synchronicity``).
    module_registration_path = f"{args.runtime_package}.module"
    try:
        registration_pkg = importlib.import_module(module_registration_path)
    except ImportError as e:
        print(
            f"Error: cannot import {module_registration_path!r} "
            f"(needed to recognize Module instances for --runtime-package): {e}",
            file=sys.stderr,
        )
        sys.exit(2)
    Module = getattr(registration_pkg, "Module", None)
    if Module is None:
        print(
            f"Error: {module_registration_path!r} has no attribute 'Module'.",
            file=sys.stderr,
        )
        sys.exit(2)

    print("Importing modules for codegen...", file=sys.stderr)

    module_objects = []
    for module_name in args.modules:
        print(f"  Importing module: {module_name}", file=sys.stderr)
        imported_module = importlib.import_module(module_name)

        for attr_name in dir(imported_module):
            attr = getattr(imported_module, attr_name)
            if isinstance(attr, Module):
                module_objects.append(attr)
                print(
                    f"  Found Module: {attr.target_module} (synchronizer={attr.synchronizer_name!r}) "
                    f"with {len(attr._module_items())} items",
                    file=sys.stderr,
                )

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
        print("  @wrapper_module.wrap_function()", file=sys.stderr)
        sys.exit(1)

    total_items = sum(len(m._module_items()) for m in module_objects)
    print(f"\nTotal registered items: {total_items}", file=sys.stderr)

    print("Compiling wrappers...", file=sys.stderr)

    try:
        modules = compile_modules(
            module_objects,
            runtime_package=args.runtime_package,
        )
    except (TypeError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not modules:
        print("No modules generated", file=sys.stderr)
        sys.exit(1)

    print(f"Generated {len(modules)} module(s)", file=sys.stderr)

    if args.stdout:
        if args.ruff:
            print("Running ruff to format generated files...", file=sys.stderr)
            with tempfile.TemporaryDirectory() as tmpdir:
                tmppath = Path(tmpdir)
                temp_files = {}
                for module_path in write_modules(tmppath, modules):
                    module_name = module_path.stem
                    temp_files[module_name] = module_path

                for module_name in sorted(temp_files.keys()):
                    file_path = temp_files[module_name]
                    run_ruff_on_file(file_path)
                    print(f"  Formatted: {module_name}", file=sys.stderr)

                for module_name in sorted(temp_files.keys()):
                    file_path = temp_files[module_name]
                    module_path_str = module_name.replace(".", "/") + ".py"
                    print(f"# File: {module_path_str}\n")
                    print(file_path.read_text())
                    print()
        else:
            for module_name in sorted(modules.keys()):
                module_path = module_name.replace(".", "/") + ".py"
                print(f"# File: {module_path}\n")
                print(modules[module_name])
                print()
    else:
        output_dir = Path(args.output_dir)
        written_files = []
        for module_path in write_modules(output_dir, modules):
            written_files.append(module_path)
            print(f"  Wrote: {module_path}", file=sys.stderr)

        if args.ruff:
            print("\nRunning ruff to format generated files...", file=sys.stderr)
            for file_path in written_files:
                run_ruff_on_file(file_path)
                print(f"  Formatted: {file_path}", file=sys.stderr)

        print("\nCompilation completed successfully!", file=sys.stderr)


def main() -> None:
    """Main CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "vendor":
        _run_vendor(args)
    elif args.command == "wrappers":
        _run_wrappers(args)
    else:  # pragma: no cover
        parser.error(f"unknown command {args.command!r}")


if __name__ == "__main__":
    main()
