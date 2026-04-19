"""Consumer typing checks for generated simple_function wrappers."""

import subprocess
from typing import assert_type

import simple_function

x = simple_function.simple_add(1, 2)
assert_type(x, int)

y = simple_function.greet()
assert_type(y, str)

y = simple_function.default_pipe()
assert_type(y, int)
assert y == subprocess.PIPE

y = simple_function.returns_awaitable()
assert_type(y, str)
