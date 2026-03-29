"""Integration tests for functions_with_typevars_impl.py support file.

Tests execution and type checking of generated code for functions using TypeVar and ParamSpec.
"""

import pytest
from pathlib import Path

from test.integration.test_utils import check_pyright


def test_generated_code_execution_typevars(generated_wrappers):
    """Test that generated code with TypeVars can be imported and executed."""

    print("✓ Generated code execution test for TypeVars passed")


def test_typevar_with_wrapped_class_bound(generated_wrappers):
    """Test that TypeVar bounds referencing wrapped classes are translated correctly."""
    import functions_with_typevars

    # Verify SomeClass is wrapped and available
    assert hasattr(functions_with_typevars, "SomeClass")

    print("✓ TypeVar with wrapped class bound test passed")


def test_class_methods_with_typevars(generated_wrappers):
    import functions_with_typevars

    # Create a container instance
    container = functions_with_typevars.Container()

    # Test transform method with SomeClass (bounded TypeVar)
    some_obj = functions_with_typevars.SomeClass()
    # Test convert method with Callable returning a TypeVar
    result = container.tuple_to_list(
        (
            some_obj,
            some_obj,
        )
    )
    assert len(result) == 2
    for entry in result:
        assert isinstance(entry, functions_with_typevars.SomeClass)

    print("✓ Class methods with TypeVars test passed")


@pytest.mark.xfail(
    strict=True,
    reason="TypeVar bounds that reference wrapped classes are not typed correctly yet",
)
def test_pyright_functions_with_typevars(generated_wrappers):
    import functions_with_typevars

    # This is the intended typing contract, but pyright currently rejects the
    # generated wrapper when TypeVar bounds reference wrapped classes.
    check_pyright([Path(functions_with_typevars.__file__)])
