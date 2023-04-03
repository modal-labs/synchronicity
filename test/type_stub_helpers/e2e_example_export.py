# This file creates wrapped entities for async implementation in e2e_example_impl.py
# This file is then used as input for generating type stubs
from typing import Optional

import synchronicity
from . import e2e_example_impl

synchronizer = synchronicity.Synchronizer()
BlockingFoo = synchronizer.create_blocking(
    e2e_example_impl._Foo, "BlockingFoo", __name__
)

some_instance: Optional[BlockingFoo] = None

_T_Blocking = synchronizer.create_blocking(
    e2e_example_impl._T, "_T_Blocking", __name__
)  # synchronize the TypeVar to support translation of bounds
listify = synchronizer.create_blocking(e2e_example_impl._listify, "listify", __name__)

overloaded = synchronizer.create_blocking(
    e2e_example_impl._overloaded, "overloaded", __name__
)
