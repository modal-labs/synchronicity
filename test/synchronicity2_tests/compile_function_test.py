import asyncio
import pytest
import typing
from typing import Dict, List, Optional

from synchronicity.codegen.compile import compile_function
from synchronicity.synchronizer import Synchronizer


# Test fixtures
@pytest.fixture
def test_synchronizer():
    """Create a test synchronizer for testing"""
    return Synchronizer("test_synchronizer")


@pytest.fixture
def simple_function():
    """Simple function with basic types"""

    async def func(x: int) -> str:
        await asyncio.sleep(0.01)
        return f"Result: {x}"

    return func


@pytest.fixture
def complex_function():
    """Function with complex type annotations"""

    async def func(
        items: List[str], config: Dict[str, int], optional_param: Optional[str] = None
    ) -> Dict[str, List[int]]:
        await asyncio.sleep(0.01)
        return {"processed": [len(item) for item in items]}

    return func


@pytest.fixture
def no_annotation_function():
    """Function without type annotations"""

    async def func(x, y=42):
        await asyncio.sleep(0.01)
        return x + y

    return func


@pytest.fixture
def async_generator_function():
    """Async generator function"""

    async def func(items: List[str]) -> typing.AsyncGenerator[str, None]:
        for item in items:
            await asyncio.sleep(0.01)
            yield f"processed: {item}"

    return func


@pytest.fixture
def generic_types_function():
    """Function with generic type arguments like list[str], dict[str, int]"""

    async def func(items: list[str], mapping: dict[str, int], optional_set: set[int] = None) -> list[dict[str, int]]:
        await asyncio.sleep(0.01)
        result = []
        for item in items:
            if item in mapping:
                result.append({item: mapping[item]})
        return result

    return func


def test_compile_function_basic_types(test_synchronizer, simple_function):
    """Test _compile_function with basic type annotations"""
    test_synchronizer.wrap(target_module="test_module")(simple_function)

    # Get the wrapped function
    wrapped_func = None
    for func, (module, name) in test_synchronizer._wrapped.items():
        if func.__name__ == simple_function.__name__:
            wrapped_func = func
            break

    assert wrapped_func is not None, "Function should be wrapped"

    # Generate code
    generated_code = compile_function(wrapped_func, test_synchronizer)
    print(generated_code)
    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify it contains expected elements
    # Implementation should reference the actual module where func is defined
    assert f"impl_function = {wrapped_func.__module__}." in generated_code
    assert "(AioWrapper):" in generated_code  # Inherits from AioWrapper
    assert "async def aio(self" in generated_code
    assert "_run_function_sync" in generated_code
    assert "await impl_function" in generated_code
    assert "@wrapped_function(_" in generated_code

    # Verify type annotations are preserved
    assert "x: int" in generated_code
    assert "-> str" in generated_code


def test_compile_function_complex_types(test_synchronizer, complex_function):
    """Test _compile_function with complex type annotations"""
    test_synchronizer.wrap(target_module="test_module")(complex_function)

    # Get the wrapped function
    wrapped_func = None
    for func, (module, name) in test_synchronizer._wrapped.items():
        if func.__name__ == complex_function.__name__:
            wrapped_func = func
            break

    assert wrapped_func is not None, "Function should be wrapped"

    # Generate code
    generated_code = compile_function(wrapped_func, test_synchronizer)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify complex types are preserved (now using lowercase list/dict)
    assert "items: list" in generated_code
    assert "config: dict" in generated_code
    # Optional types can be Union[str, None] or int | None depending on Python version
    assert (
        "optional_param: typing.Union[str, None]" in generated_code
        or "optional_param: int | None" in generated_code
        or "optional_param: typing.Optional" in generated_code
    )
    assert "-> dict" in generated_code
    assert "= None" in generated_code  # Default parameter


def test_compile_function_no_annotations(test_synchronizer, no_annotation_function):
    """Test _compile_function with no type annotations"""
    test_synchronizer.wrap(target_module="test_module")(no_annotation_function)

    # Get the wrapped function
    wrapped_func = None
    for func, (module, name) in test_synchronizer._wrapped.items():
        if func.__name__ == no_annotation_function.__name__:
            wrapped_func = func
            break

    assert wrapped_func is not None, "Function should be wrapped"

    # Generate code
    generated_code = compile_function(wrapped_func, test_synchronizer)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify parameters without annotations are handled in aio method
    assert "async def aio(self, x, y = 42)" in generated_code
    # __call__ is now handled by AioWrapper base class
    # No return type annotation since there wasn't one in the original


def test_compile_function_template_pattern(test_synchronizer, simple_function):
    """Test that the generated code follows the template pattern exactly"""
    test_synchronizer.wrap(target_module="test_module")(simple_function)

    # Get the wrapped function
    wrapped_func = None
    for func, (module, name) in test_synchronizer._wrapped.items():
        if func.__name__ == simple_function.__name__:
            wrapped_func = func
            break

    generated_code = compile_function(wrapped_func, test_synchronizer)

    # Check that the generated code contains all expected template elements
    template_elements = [
        "class _",
        "(AioWrapper):",  # Now inherits from AioWrapper
        "async def aio(self",
        "_run_function_sync",
        "await impl_function",
        "@wrapped_function(_",
    ]

    for element in template_elements:
        assert element in generated_code, f"Generated code should contain '{element}'"

    # Verify the structure - class definition should inherit from AioWrapper
    lines = generated_code.split("\n")
    class_line = None
    for i, line in enumerate(lines):
        if line.startswith("class _"):
            class_line = i
            break

    assert class_line is not None, "Should have a class definition"
    assert "(AioWrapper):" in lines[class_line], "Should inherit from AioWrapper"


def test_compile_function_multiple_functions(test_synchronizer, simple_function, complex_function):
    """Test _compile_function with multiple wrapped functions"""
    test_synchronizer.wrap(target_module="test_module")(simple_function)
    test_synchronizer.wrap(target_module="test_module")(complex_function)

    # Should have 2 wrapped functions
    assert len(test_synchronizer._wrapped) == 2

    # Each should generate valid code
    for func, (target_module, target_name) in test_synchronizer._wrapped.items():
        generated_code = compile_function(func, test_synchronizer)

        # Should compile without errors
        compile(generated_code, "<string>", "exec")

        # Should contain the template pattern
        assert "class _" in generated_code
        assert "(AioWrapper):" in generated_code  # Inherits from AioWrapper
        assert "impl_function = " in generated_code
        assert "async def aio(" in generated_code
        assert "@wrapped_function(_" in generated_code


def test_compile_function_async_generator(test_synchronizer, async_generator_function):
    """Test _compile_function with async generator function"""
    test_synchronizer.wrap(target_module="test_module")(async_generator_function)

    # Get the wrapped function
    wrapped_func = None
    for func, (module, name) in test_synchronizer._wrapped.items():
        if func.__name__ == async_generator_function.__name__:
            wrapped_func = func
            break

    assert wrapped_func is not None, "Function should be wrapped"

    # Generate code
    generated_code = compile_function(wrapped_func, test_synchronizer)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify it uses generator methods instead of function methods
    assert "_run_generator_sync" in generated_code
    assert "_run_generator_async" in generated_code
    assert "_run_function_sync" not in generated_code

    # Verify it yields from the generator instead of returning
    assert "yield from get_synchronizer" in generated_code
    assert "async for item in self._synchronizer._run_generator_async(gen):" in generated_code
    assert "yield item" in generated_code
    assert "gen = impl_function" in generated_code

    # Verify return type annotations for generators
    assert "-> typing.Generator[str" in generated_code  # Sync version returns Generator
    assert (
        "-> typing.AsyncGenerator[str, None]" in generated_code
    )  # Async version returns AsyncGenerator with type args

    # Verify parameter types are preserved
    assert "items: list" in generated_code


def test_compile_function_async_generator_template_pattern(test_synchronizer, async_generator_function):
    """Test that async generator functions follow the template pattern"""
    test_synchronizer.wrap(target_module="test_module")(async_generator_function)

    # Get the wrapped function
    wrapped_func = None
    for func, (module, name) in test_synchronizer._wrapped.items():
        if func.__name__ == async_generator_function.__name__:
            wrapped_func = func
            break

    generated_code = compile_function(wrapped_func, test_synchronizer)

    # Check that the generated code contains all expected template elements
    template_elements = [
        "class _",
        "(AioWrapper):",  # Inherits from AioWrapper
        "async def aio(self",
        "@wrapped_function(_",
    ]

    for element in template_elements:
        assert element in generated_code, f"Generated code should contain '{element}'"

    # Verify the structure is correct for generators
    assert "gen = impl_function(" in generated_code
    assert "yield from" in generated_code
    assert "async for" in generated_code


def test_compile_function_generic_types(test_synchronizer, generic_types_function):
    """Test _compile_function with generic type arguments like list[str], dict[str, int]"""
    test_synchronizer.wrap(target_module="test_module")(generic_types_function)

    # Get the wrapped function
    wrapped_func = None
    for func, (module, name) in test_synchronizer._wrapped.items():
        if func.__name__ == generic_types_function.__name__:
            wrapped_func = func
            break

    assert wrapped_func is not None, "Function should be wrapped"

    # Generate code
    generated_code = compile_function(wrapped_func, test_synchronizer)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify generic types are preserved in parameter annotations
    assert "items: list[str]" in generated_code
    assert "mapping: dict[str, int]" in generated_code
    assert "optional_set: set[int]" in generated_code

    # Verify generic types are preserved in return annotation
    assert "-> list[dict[str, int]]" in generated_code  # Sync version
    assert "-> list[dict[str, int]]" in generated_code  # Async version should be the same for non-awaitable

    # Verify default parameter handling
    assert "= None" in generated_code

    # Verify it contains expected template elements
    assert "class _" in generated_code
    assert "(AioWrapper):" in generated_code  # Inherits from AioWrapper
    assert f"impl_function = {wrapped_func.__module__}." in generated_code
    assert "async def aio(self" in generated_code


def test_compile_unwrapped_async_function_raises_error(test_synchronizer):
    """Test that compiling an async function not in the wrapped dict raises an error."""

    async def unwrapped_async_func(x: int) -> str:
        await asyncio.sleep(0.01)
        return f"Result: {x}"

    # This should raise a ValueError because the function is async but not wrapped
    with pytest.raises(ValueError, match="Function unwrapped_async_func.*not in the synchronizer's wrapped dict"):
        compile_function(unwrapped_async_func, test_synchronizer)


def test_compile_unwrapped_sync_function_raises_error(test_synchronizer):
    """Test that compiling a sync function not in the wrapped dict raises an error."""

    def unwrapped_sync_func(x: int) -> str:
        return f"Result: {x}"

    # This should raise a ValueError because the function is not wrapped
    with pytest.raises(ValueError, match="Function unwrapped_sync_func.*not in the synchronizer's wrapped dict"):
        compile_function(unwrapped_sync_func, test_synchronizer)


def test_compile_async_generator_with_wrapped_type_quoting(test_synchronizer):
    """Test that async generators with wrapped types quote the entire return type annotation.

    When a generator yields wrapped types (e.g., AsyncGenerator[Person, None]),
    the entire return type should be quoted as a string for forward reference safety,
    not just individual parts within the generic.

    We want: -> "typing.Generator[Person, None, None]"
    Not: -> typing.Generator["Person", None, None]
    """

    # Create a wrapped class
    @test_synchronizer.wrap(target_module="test_module")
    class Person:
        def __init__(self, name: str):
            self.name = name

    # Create an async generator that yields the wrapped type
    @test_synchronizer.wrap(target_module="test_module")
    async def stream_people(count: int) -> typing.AsyncIterator[Person]:
        """Stream people instances."""
        for i in range(count):
            yield Person(f"Person {i}")

    # Get the wrapped function
    wrapped_func = None
    for func, (module, name) in test_synchronizer._wrapped.items():
        if func.__name__ == "stream_people":
            wrapped_func = func
            break

    assert wrapped_func is not None, "Function should be wrapped"

    # Generate code
    generated_code = compile_function(wrapped_func, test_synchronizer)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # The key assertion: the entire return type should be quoted as a string
    # for both sync and async versions when it contains wrapper types
    assert (
        ' -> "typing.Generator[Person, None, None]"' in generated_code
    ), "Sync version should quote entire Generator type when it contains wrapped types"
    assert (
        ' -> "typing.AsyncGenerator[Person]"' in generated_code
    ), "Async version should quote entire AsyncGenerator type when it contains wrapped types"

    # Should NOT have individually quoted type arguments inside the generic
    assert 'Generator["Person"' not in generated_code, "Should not quote individual type arguments within the generic"
    assert (
        'AsyncGenerator["Person"' not in generated_code
    ), "Should not quote individual type arguments within the generic"


def test_compile_async_generator_with_nested_wrapped_type_quoting(test_synchronizer):
    """Test that async generators with nested wrapped types (e.g., list[Person]) quote the entire return type."""

    # Create a wrapped class
    @test_synchronizer.wrap(target_module="test_module")
    class Person:
        def __init__(self, name: str):
            self.name = name

    # Create an async generator that yields lists of the wrapped type
    @test_synchronizer.wrap(target_module="test_module")
    async def stream_person_batches(batch_size: int) -> typing.AsyncIterator[List[Person]]:
        """Stream batches of people."""
        batch = []
        for i in range(10):
            batch.append(Person(f"Person {i}"))
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    # Get the wrapped function
    wrapped_func = None
    for func, (module, name) in test_synchronizer._wrapped.items():
        if func.__name__ == "stream_person_batches":
            wrapped_func = func
            break

    assert wrapped_func is not None, "Function should be wrapped"

    # Generate code
    generated_code = compile_function(wrapped_func, test_synchronizer)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # The entire return type should be quoted because it contains wrapped types
    assert (
        ' -> "typing.Generator[list[Person], None, None]"' in generated_code
    ), "Sync version should quote entire Generator type when yield type contains wrapped types"
    assert (
        ' -> "typing.AsyncGenerator[list[Person]]"' in generated_code
    ), "Async version should quote entire AsyncGenerator type when yield type contains wrapped types"
