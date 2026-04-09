"""Consumer typing checks for functions_with_typevars wrappers."""

from typing import assert_type

import functions_with_typevars


def _usage() -> None:
    container = functions_with_typevars.Container()
    some_obj = functions_with_typevars.SomeClass()
    result = container.tuple_to_list((some_obj, some_obj))
    assert_type(result, list[functions_with_typevars.SomeClass])
    for entry in result:
        assert_type(entry, functions_with_typevars.SomeClass)
