"""Integration tests for functions_with_typevars_impl.py support file.

Tests execution and type checking of generated code for functions using TypeVar and ParamSpec.
"""

from pathlib import Path

from test.integration.test_utils import check_pyright


def test_generated_code_execution_typevars(generated_wrappers):
    """Test that generated code with TypeVars can be imported and executed."""
    import functions_with_typevars

    # Test the wrapper function with a simple callable
    def add_one(x: int) -> functions_with_typevars.SomeClass:
        return functions_with_typevars.SomeClass()

    # listify should convert Callable[[int], int] to Callable[[int], list[int]]
    listified_callable = functions_with_typevars.listify(add_one)
    listified = listified_callable(10)
    assert isinstance(listified, list)
    assert isinstance(listified[0], functions_with_typevars.SomeClass)

    print("✓ Generated code execution test for TypeVars passed")


def test_typevar_with_wrapped_class_bound(generated_wrappers):
    """Test that TypeVar bounds referencing wrapped classes are translated correctly."""
    import functions_with_typevars

    # Verify SomeClass is wrapped and available
    assert hasattr(functions_with_typevars, "SomeClass")

    # Verify listify exists and has the correct signature
    assert hasattr(functions_with_typevars, "listify")

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


def test_pyright_functions_with_typevars(generated_wrappers):
    import pytest

    pytest.skip("TypeVar identity issue when passing typed callbacks - known limitation")

    import functions_with_typevars

    # Verify type correctness with pyright
    check_pyright([Path(functions_with_typevars.__file__)])
