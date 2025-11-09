from typing import assert_type, reveal_type

import custom_iterators

custom_iterator = custom_iterators.CustomAsyncIterator([1, 2, 3])
reveal_type(custom_iterator.__iter__)
assert_type(next(custom_iterator), int)
assert assert_type(next(custom_iterator), int)

it = custom_iterators.IterableClassUsingGeneratorTyped()
assert_type(next(iter(it)), int)
