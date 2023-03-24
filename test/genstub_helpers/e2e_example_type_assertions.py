# this code is only meant to be "running" through mypy and not an actual python interpreter!

from test.genstub_helpers.e2e_example_export import BlockingFoo
from typing_extensions import assert_type

b = BlockingFoo("hello")

assert_type(b, BlockingFoo)

assert_type(b.getarg(), str)
