from typing import Optional

import synchronicity
from .e2e_example_impl import _Foo

synchronizer = synchronicity.Synchronizer()
BlockingFoo = synchronizer.create_blocking(
    _Foo, "BlockingFoo", "test.genstub_helpers.e2e_example_export"
)

some_instance: Optional[BlockingFoo] = None
