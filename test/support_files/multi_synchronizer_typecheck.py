"""Consumer typing checks for multi_sync wrappers."""

from typing import assert_type

import multi_sync.a
import multi_sync.b


def _usage() -> None:
    ta = multi_sync.a.thread_and_loop_a()
    tb = multi_sync.b.thread_and_loop_b()
    assert_type(ta, tuple[int, int])
    assert_type(tb, tuple[int, int])
