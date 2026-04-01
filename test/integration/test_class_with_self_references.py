"""Integration tests for class_with_translation_impl.py support file.

Tests execution and type checking of generated code for classes requiring type translation.
"""

import pytest
from pathlib import Path

from test.integration.test_utils import check_pyright, check_pyright_with_xfail


@pytest.mark.xfail(reason="known bug: quoted named references aren't emitted with quotes")
def test_runtime(generated_wrappers):
    # check that actual invokations of the wrappers work correctly
    import class_with_self_references

    a = class_with_self_references.SomeClass()
    assert a.accept_self(a) is a
    assert a.accept_self_by_name(a) is a


def test_pyright_implementation(generated_wrappers):
    # check that the implementation type checks correctly
    import class_with_translation_impl

    check_pyright([Path(class_with_translation_impl.__file__)])


def test_pyright_wrapper(generated_wrappers, support_files):
    # check that usage of the generated wrapper type checks correctly
    check_pyright_with_xfail("class_with_self_references_typecheck")
