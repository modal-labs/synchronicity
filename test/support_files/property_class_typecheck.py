"""Consumer typing checks for generated property_class wrappers."""

from typing import assert_type

import property_class


def _sync_usage() -> None:
    settings = property_class.Settings("test", 5)

    # Read-only property
    assert_type(settings.name, str)

    # Read-write property
    assert_type(settings.max_retries, int)
    settings.max_retries = 10

    # Computed read-only property
    assert_type(settings.call_count, int)

    # Wrapped type property
    assert_type(settings.tag, property_class.Tag)
    settings.tag = property_class.Tag("new")

    # Async method still works
    result = settings.do_work()
    assert_type(result, str)
