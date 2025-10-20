import asyncio
import pytest
import typing
from typing import Dict, List, Optional

from synchronicity2.compile import compile_function
from synchronicity2.synchronizer import Library


# Test fixtures
@pytest.fixture
def test_library():
    """Create a test library for testing"""
    return Library("test_library")


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


def test_compile_function_basic_types(test_library, simple_function):
    """Test _compile_function with basic type annotations"""
    test_library.wrap(target_module="test_module")(simple_function)

    # Get the wrapped function
    wrapped_func = None
    target_module = None
    for func, (module, name) in test_library._wrapped.items():
        if func.__name__ == simple_function.__name__:
            wrapped_func = func
            target_module = module
            break

    assert wrapped_func is not None, "Function should be wrapped"

    # Generate code
    generated_code = compile_function(wrapped_func, target_module, test_library._synchronizer_name)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify it contains expected elements
    assert "class _" in generated_code
    assert "Wrapper:" in generated_code
    assert "synchronizer = get_synchronizer(" in generated_code
    assert "impl_function = test_module." in generated_code
    assert "def __call__(self" in generated_code
    assert "async def aio(self" in generated_code
    assert "_run_function_sync" in generated_code
    assert "_run_function_async" in generated_code
    assert f"{simple_function.__name__} = _" in generated_code

    # Verify type annotations are preserved
    assert "x: int" in generated_code
    assert "-> str" in generated_code


def test_compile_function_complex_types(test_library, complex_function):
    """Test _compile_function with complex type annotations"""
    test_library.wrap(target_module="test_module")(complex_function)

    # Get the wrapped function
    wrapped_func = None
    target_module = None
    for func, (module, name) in test_library._wrapped.items():
        if func.__name__ == complex_function.__name__:
            wrapped_func = func
            target_module = module
            break

    assert wrapped_func is not None, "Function should be wrapped"

    # Generate code
    generated_code = compile_function(wrapped_func, target_module, test_library._synchronizer_name)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify complex types are preserved
    assert "items: typing.List" in generated_code
    assert "config: typing.Dict" in generated_code
    assert "optional_param: typing.Optional" in generated_code
    assert "-> typing.Dict" in generated_code
    assert "= None" in generated_code  # Default parameter


def test_compile_function_no_annotations(test_library, no_annotation_function):
    """Test _compile_function with no type annotations"""
    test_library.wrap(target_module="test_module")(no_annotation_function)

    # Get the wrapped function
    wrapped_func = None
    target_module = None
    for func, (module, name) in test_library._wrapped.items():
        if func.__name__ == no_annotation_function.__name__:
            wrapped_func = func
            target_module = module
            break

    assert wrapped_func is not None, "Function should be wrapped"

    # Generate code
    generated_code = compile_function(wrapped_func, target_module, test_library._synchronizer_name)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify parameters without annotations are handled
    assert "def __call__(self, x, y = 42)" in generated_code
    assert "async def aio(self, x, y = 42)" in generated_code
    # No return type annotation since there wasn't one in the original


def test_compile_function_template_pattern(test_library, simple_function):
    """Test that the generated code follows the template pattern exactly"""
    test_library.wrap(target_module="test_module")(simple_function)

    # Get the wrapped function
    wrapped_func = None
    target_module = None
    for func, (module, name) in test_library._wrapped.items():
        if func.__name__ == simple_function.__name__:
            wrapped_func = func
            target_module = module
            break

    generated_code = compile_function(wrapped_func, target_module, test_library._synchronizer_name)

    # Check that the generated code contains all expected template elements
    template_elements = [
        "class _",
        "Wrapper:",
        "synchronizer = get_synchronizer(",
        "impl_function = test_module.",
        "def __call__(self",
        "async def aio(self",
        "_run_function_sync",
        "_run_function_async",
        f"{simple_function.__name__} = _",
    ]

    for element in template_elements:
        assert element in generated_code, f"Generated code should contain '{element}'"

    # Verify the structure matches the template
    lines = generated_code.split("\n")
    class_line = None
    for i, line in enumerate(lines):
        if line.startswith("class _"):
            class_line = i
            break

    assert class_line is not None, "Should have a class definition"
    assert "synchronizer = get_synchronizer(" in lines[class_line + 1], "Should have synchronizer attribute"
    assert "impl_function = test_module." in lines[class_line + 2], "Should have impl_function attribute"


def test_compile_function_multiple_functions(test_library, simple_function, complex_function):
    """Test _compile_function with multiple wrapped functions"""
    test_library.wrap(target_module="test_module")(simple_function)
    test_library.wrap(target_module="test_module")(complex_function)

    # Should have 2 wrapped functions
    assert len(test_library._wrapped) == 2

    # Each should generate valid code
    for func, (target_module, target_name) in test_library._wrapped.items():
        generated_code = compile_function(func, target_module, test_library._synchronizer_name)

        # Should compile without errors
        compile(generated_code, "<string>", "exec")

        # Should contain the template pattern
        assert "class _" in generated_code
        assert "synchronizer = get_synchronizer(" in generated_code
        assert "impl_function = " in generated_code
        assert "def __call__(" in generated_code
        assert "async def aio(" in generated_code
        assert f"{func.__name__} = " in generated_code


def test_compile_function_async_generator(test_library, async_generator_function):
    """Test _compile_function with async generator function"""
    test_library.wrap(target_module="test_module")(async_generator_function)

    # Get the wrapped function
    wrapped_func = None
    target_module = None
    for func, (module, name) in test_library._wrapped.items():
        if func.__name__ == async_generator_function.__name__:
            wrapped_func = func
            target_module = module
            break

    assert wrapped_func is not None, "Function should be wrapped"

    # Generate code
    generated_code = compile_function(wrapped_func, target_module, test_library._synchronizer_name)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify it uses generator methods instead of function methods
    assert "_run_generator_sync" in generated_code
    assert "_run_generator_async" in generated_code
    assert "_run_function_sync" not in generated_code
    assert "_run_function_async" not in generated_code

    # Verify it yields from the generator instead of returning
    assert "yield from self.synchronizer._run_generator_sync(gen)" in generated_code
    assert "async for item in self.synchronizer._run_generator_async(gen):" in generated_code
    assert "yield item" in generated_code

    # Verify return type annotations for generators
    assert "-> typing.Iterator[str]" in generated_code  # Sync version returns Iterator
    assert (
        "-> typing.AsyncGenerator[str, None]" in generated_code
    )  # Async version returns AsyncGenerator with type args

    # Verify parameter types are preserved
    assert "items: typing.List" in generated_code


def test_compile_function_async_generator_template_pattern(test_library, async_generator_function):
    """Test that async generator functions follow the template pattern"""
    test_library.wrap(target_module="test_module")(async_generator_function)

    # Get the wrapped function
    wrapped_func = None
    target_module = None
    for func, (module, name) in test_library._wrapped.items():
        if func.__name__ == async_generator_function.__name__:
            wrapped_func = func
            target_module = module
            break

    generated_code = compile_function(wrapped_func, target_module, test_library._synchronizer_name)

    # Check that the generated code contains all expected template elements
    template_elements = [
        "class _",
        "Wrapper:",
        "synchronizer = get_synchronizer(",
        "impl_function = test_module.",
        "def __call__(self",
        "async def aio(self",
        f"{async_generator_function.__name__} = _",
    ]

    for element in template_elements:
        assert element in generated_code, f"Generated code should contain '{element}'"

    # Verify the structure is correct for generators
    assert "gen = self.impl_function(" in generated_code
    assert "yield from" in generated_code
    assert "async for" in generated_code


def test_compile_function_generic_types(test_library, generic_types_function):
    """Test _compile_function with generic type arguments like list[str], dict[str, int]"""
    test_library.wrap(target_module="test_module")(generic_types_function)

    # Get the wrapped function
    wrapped_func = None
    target_module = None
    for func, (module, name) in test_library._wrapped.items():
        if func.__name__ == generic_types_function.__name__:
            wrapped_func = func
            target_module = module
            break

    assert wrapped_func is not None, "Function should be wrapped"

    # Generate code
    generated_code = compile_function(wrapped_func, target_module, test_library._synchronizer_name)

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
    assert "synchronizer = get_synchronizer(" in generated_code
    assert "impl_function = test_module." in generated_code
    assert "def __call__(self" in generated_code
    assert "async def aio(self" in generated_code
