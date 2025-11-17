# This file creates wrapped entities for async implementation in e2e_example_impl.py
# This file is then used as input for generating type stubs
from typing import Optional

import synchronicity

from . import e2e_example_impl

synchronizer = synchronicity.Synchronizer()
BlockingFoo = synchronizer.wrap(e2e_example_impl._Foo, "BlockingFoo", __name__)

some_instance: Optional[BlockingFoo] = None

_T_Blocking = synchronizer.wrap(
    e2e_example_impl._T, "_T_Blocking", __name__
)  # synchronize the TypeVar to support translation of bounds
listify = synchronizer.wrap(e2e_example_impl._listify, "listify", __name__)

overloaded = synchronizer.wrap(e2e_example_impl._overloaded, "overloaded", __name__)

returns_foo = synchronizer.wrap(e2e_example_impl._returns_foo, "returns_foo", __name__)

wrapped_make_context = synchronizer.wrap(e2e_example_impl.make_context, "make_context", __name__)

# TODO: we shouldn't need to wrap typevars unless they have wrapped `bounds`
P = synchronizer.wrap(e2e_example_impl.P, "P", __name__)
R = synchronizer.wrap(e2e_example_impl.R, "R", __name__)


CallableWrapper = synchronizer.wrap(e2e_example_impl.CallableWrapper, "CallableWrapper", __name__)

wrap_callable = synchronizer.wrap(e2e_example_impl.wrap_callable, "wrap_callable", __name__)


SomeGeneric = synchronizer.wrap(e2e_example_impl.SomeGeneric, "SomeGeneric", __name__)
