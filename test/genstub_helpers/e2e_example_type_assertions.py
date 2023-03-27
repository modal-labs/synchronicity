# this code is only meant to be "running" through mypy and not an actual python interpreter!
import typing

from test.genstub_helpers import e2e_example_export
from typing_extensions import assert_type

b = e2e_example_export.BlockingFoo("hello")

# assert start
assert_type(b, e2e_example_export.BlockingFoo)

assert_type(b.getarg(), str)
assert_type(b.gen(), typing.Generator[int, None, None])

assert_type(
    e2e_example_export.some_instance, typing.Optional[e2e_example_export.BlockingFoo]
)
