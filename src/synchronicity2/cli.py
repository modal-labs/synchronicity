#!/usr/bin/env python3
"""
Command line interface for synchronicity2 compilation.
"""

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

from synchronicity2.synchronizer import Library


def load_object_from_file(file_path: str, object_ref: str) -> Any:
    """
    Load an object from a Python file using its reference.

    Args:
        file_path: Path to the Python file
        object_ref: Dot-separated reference to the object (e.g., 'my_module.my_object')

    Returns:
        The loaded object
    """
    # Convert to absolute path
    file_path = Path(file_path).resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not file_path.suffix == ".py":
        raise ValueError(f"File must be a Python file (.py): {file_path}")

    # Load the module
    module_name = file_path.stem
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {file_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Get the object reference
    obj = module
    for attr in object_ref.split("."):
        if not hasattr(obj, attr):
            raise AttributeError(f"Object '{object_ref}' not found in {file_path}")
        obj = getattr(obj, attr)

    return obj


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Compile a synchronicity2.Library object from a Python file")
    parser.add_argument("file_path", help="Path to the Python file containing the Library object")
    parser.add_argument("object_ref", help="Dot-separated reference to the Library object (e.g., 'my_sync')")

    args = parser.parse_args()

    # Load the object from the file
    obj = load_object_from_file(args.file_path, args.object_ref)

    # Assert that it's a Library object
    if not isinstance(obj, Library):
        raise TypeError(f"Object '{args.object_ref}' is not a synchronicity2.Library instance. Got: {type(obj)}")

    # Call compile() on the object
    print(f"Compiling Library: {args.object_ref}", file=sys.stderr)
    result = obj.compile()

    print("Compilation completed successfully!", file=sys.stderr)
    if result is not None:
        print(f"Result: {result}", file=sys.stderr)


if __name__ == "__main__":
    main()
