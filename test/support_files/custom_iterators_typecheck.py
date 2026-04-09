"""Consumer typing checks for custom_iterators wrappers."""

from typing import assert_type

import custom_iterators

custom_iterator = custom_iterators.CustomAsyncIterator([1, 2, 3])
assert_type(next(iter(custom_iterator)), int)

it = custom_iterators.IterableClassUsingGeneratorTyped()
assert_type(next(iter(it)), int)
