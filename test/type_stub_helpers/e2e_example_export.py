# This file creates wrapped entities for async implementation in e2e_example_impl.py
# This file is then used as input for generating type stubs
from typing import Optional

import synchronicity

from . import e2e_example_impl

synchronizer = synchronicity.Synchronizer()
BlockingFoo = synchronizer.create_blocking(e2e_example_impl._Foo, "BlockingFoo", __name__)

some_instance: Optional[BlockingFoo] = None

_T_Blocking = synchronizer.create_blocking(
    e2e_example_impl._T, "_T_Blocking", __name__
)  # synchronize the TypeVar to support translation of bounds
listify = synchronizer.create_blocking(e2e_example_impl._listify, "listify", __name__)

overloaded = synchronizer.create_blocking(e2e_example_impl._overloaded, "overloaded", __name__)

returns_foo = synchronizer.create_blocking(e2e_example_impl._returns_foo, "returns_foo", __name__)

wrapped_make_context = synchronizer.create_blocking(e2e_example_impl.make_context, "make_context", __name__)

# TODO: we shouldn't need to wrap typevars unless they have wrapped `bounds`
P = synchronizer.create_blocking(e2e_example_impl.P, "P", __name__)
R = synchronizer.create_blocking(e2e_example_impl.R, "R", __name__)


CallableWrapper = synchronizer.create_blocking(e2e_example_impl.CallableWrapper, "CallableWrapper", __name__)

wrap_callable = synchronizer.create_blocking(e2e_example_impl.wrap_callable, "wrap_callable", __name__)
