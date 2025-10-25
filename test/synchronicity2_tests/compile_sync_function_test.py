"""Tests for compiling non-async (synchronous) functions."""

import pytest

from synchronicity import get_synchronizer
from synchronicity.codegen.compile import compile_function


@pytest.fixture
def test_synchronizer():
    """Synchronizer instance for testing."""
    return get_synchronizer("test_compile_sync_function")


def test_compile_sync_function_basic(test_synchronizer):
    """Test compiling a basic synchronous function without type translation."""

    @test_synchronizer.wrap(target_module="test_module")
    def simple_add(a: int, b: int) -> int:
        return a + b

    code = compile_function(simple_add, "test_module", "test_synchronizer", test_synchronizer._wrapped)

    # Verify generated code compiles
    compile(code, "<string>", "exec")

    # Check that it doesn't use await or synchronizer
    assert "await impl_function" not in code
    assert "_run_function_sync" not in code
    assert "_run_function_async" not in code

    # Check that it calls impl_function directly
    assert "return impl_function(a, b)" in code

    # Check that there's no wrapper class or decorator
    assert "class _simple_add" not in code
    assert "@wrapped_function" not in code
    assert "async def aio" not in code


def test_compile_sync_function_with_wrapped_arg(test_synchronizer):
    """Test compiling a synchronous function that takes a wrapped type."""

    @test_synchronizer.wrap(target_module="test_module")
    class Person:
        def __init__(self, name: str):
            self.name = name

    @test_synchronizer.wrap(target_module="test_module")
    def greet(person: Person) -> str:
        return f"Hello, {person.name}"

    code = compile_function(greet, "test_module", "test_synchronizer", test_synchronizer._wrapped)

    # Verify generated code compiles
    compile(code, "<string>", "exec")

    # Check that it unwraps the argument
    assert "person_impl = person._impl_instance" in code

    # Check that it calls impl_function directly (no synchronizer)
    assert "return impl_function(person_impl)" in code
    assert "_run_function_sync" not in code

    # Check that there's no wrapper class or .aio
    assert "class _greet" not in code
    assert "@wrapped_function" not in code


def test_compile_sync_function_with_wrapped_return(test_synchronizer):
    """Test compiling a synchronous function that returns a wrapped type."""

    @test_synchronizer.wrap(target_module="test_module")
    class Person:
        def __init__(self, name: str):
            self.name = name

    @test_synchronizer.wrap(target_module="test_module")
    def create_person(name: str) -> Person:
        return Person(name)

    code = compile_function(create_person, "test_module", "test_synchronizer", test_synchronizer._wrapped)

    # Verify generated code compiles
    compile(code, "<string>", "exec")

    # Check that it wraps the return value
    assert "result = impl_function(name)" in code
    # Person is a local wrapped class in the same module, so no module prefix
    assert "return Person._from_impl(result)" in code

    # Check that it calls impl_function directly (no synchronizer)
    assert "_run_function_sync" not in code

    # Check that there's no wrapper class
    assert "class _create_person" not in code


def test_compile_sync_function_with_list_wrapped_return(test_synchronizer):
    """Test compiling a synchronous function that returns a list of wrapped types."""

    @test_synchronizer.wrap(target_module="test_module")
    class Person:
        def __init__(self, name: str):
            self.name = name

    @test_synchronizer.wrap(target_module="test_module")
    def create_people(names: list[str]) -> list[Person]:
        return [Person(name) for name in names]

    code = compile_function(create_people, "test_module", "test_synchronizer", test_synchronizer._wrapped)

    # Verify generated code compiles
    compile(code, "<string>", "exec")

    # Check that it wraps the list items
    assert "result = impl_function(names)" in code
    # Person is a local wrapped class in the same module, so no module prefix
    assert "[Person._from_impl(x) for x in result]" in code

    # Check that it calls impl_function directly (no synchronizer)
    assert "_run_function_sync" not in code

    # Check that there's no wrapper class
    assert "class _create_people" not in code


def test_compile_sync_function_no_annotations(test_synchronizer):
    """Test compiling a synchronous function without type annotations."""

    @test_synchronizer.wrap(target_module="test_module")
    def no_types(x, y):
        return x + y

    code = compile_function(no_types, "test_module", "test_synchronizer", test_synchronizer._wrapped)

    # Verify generated code compiles
    compile(code, "<string>", "exec")

    # Check that it calls impl_function directly
    assert "return impl_function(x, y)" in code
    assert "_run_function_sync" not in code


def test_compile_sync_function_with_default_args(test_synchronizer):
    """Test compiling a synchronous function with default arguments."""

    @test_synchronizer.wrap(target_module="test_module")
    def with_defaults(a: int, b: int = 10, c: str = "hello") -> str:
        return f"{a}, {b}, {c}"

    code = compile_function(with_defaults, "test_module", "test_synchronizer", test_synchronizer._wrapped)

    # Verify generated code compiles
    compile(code, "<string>", "exec")

    # Check that default values are preserved
    assert "b: int = 10" in code
    assert "c: str = 'hello'" in code

    # Check that it calls impl_function directly
    assert "return impl_function(a, b, c)" in code
