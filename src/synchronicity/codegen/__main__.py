"""Allow running synchronicity.codegen as a module.

This allows the CLI to be invoked as:
    python -m synchronicity.codegen
"""

from .cli import main

if __name__ == "__main__":
    main()
