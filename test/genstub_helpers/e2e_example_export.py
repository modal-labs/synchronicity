import synchronicity
from .e2e_example_impl import _Foo

synchronizer = synchronicity.Synchronizer()
BlockingFoo = synchronizer.create_blocking(_Foo, "BlockingFoo", "e2e_example_output")
