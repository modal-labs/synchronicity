"""Allow running synchronicity.codegen as a module.

python -m synchronicity.codegen wrappers -m my.package.impl -o out/
python -m synchronicity.codegen vendor my.lib.synchronicity -o src/
"""

from .cli import main

if __name__ == "__main__":
    main()
