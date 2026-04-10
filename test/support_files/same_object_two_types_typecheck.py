"""Consumer typing checks for same_object_two_types wrappers."""

from typing import assert_type

from same_object_two_types import Bar, Foo, bar_getter, foo_getter

foo = foo_getter()
bar = bar_getter()

assert_type(foo, Foo)
assert_type(bar, Bar)
