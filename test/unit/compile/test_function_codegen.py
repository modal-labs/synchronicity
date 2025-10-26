"""Unit tests for function code generation.

Tests the compile_function() function for various function types:
- Async functions
- Synchronous functions
- Async generators
- Functions with/without type annotations
- Functions with wrapped types
"""

import asyncio
import pytest
import typing
from typing import Dict, List, Optional

from synchronicity.codegen.compile import compile_function


# Test fixtures
@pytest.fixture
def test_synchronizer():
    """Create empty synchronized_types dict for testing."""
    return {}


class TestAsyncFunctions:
    """Tests for async function compilation."""

    @pytest.fixture
    def simple_function(self):
        """Simple function with basic types"""

        async def func(x: int) -> str:
            await asyncio.sleep(0.01)
            return f"Result: {x}"

        return func

    @pytest.fixture
    def complex_function(self):
        """Function with complex type annotations"""

        async def func(
            items: List[str], config: Dict[str, int], optional_param: Optional[str] = None
        ) -> Dict[str, List[int]]:
            await asyncio.sleep(0.01)
            return {"processed": [len(item) for item in items]}

        return func

    @pytest.fixture
    def no_annotation_function(self):
        """Function without type annotations"""

        async def func(x, y=42):
            await asyncio.sleep(0.01)
            return x + y

        return func

    @pytest.fixture
    def generic_types_function(self):
        """Function with generic type arguments like list[str], dict[str, int]"""

        async def func(
            items: list[str], mapping: dict[str, int], optional_set: set[int] = None
        ) -> list[dict[str, int]]:
            await asyncio.sleep(0.01)
            result = []
            for item in items:
                if item in mapping:
                    result.append({item: mapping[item]})
            return result

        return func

    def test_compile_function_basic_types(self, test_synchronizer, simple_function):
        """Test compile_function with basic type annotations"""
        # Generate code directly (no wrapping needed)
        generated_code = compile_function(simple_function, "test_module", "test_synchronizer", test_synchronizer)
        print(generated_code)
        # Verify the generated code compiles
        compile(generated_code, "<string>", "exec")

        # Verify it contains expected elements
        # Implementation should reference the actual module where func is defined
        assert f"impl_function = {simple_function.__module__}." in generated_code
        assert f"class _{simple_function.__name__}:" in generated_code  # Wrapper class
        assert "def __call__(self" in generated_code
        assert "async def aio(self" in generated_code
        assert "_run_function_sync" in generated_code
        assert "_run_function_async" in generated_code  # aio() should use _run_function_async
        assert f"@replace_with(_{simple_function.__name__}_instance)" in generated_code  # Uses replace_with decorator

        # Verify type annotations are preserved
        assert "x: int" in generated_code
        assert "-> str" in generated_code

    def test_compile_function_complex_types(self, test_synchronizer, complex_function):
        """Test compile_function with complex type annotations"""
        # Generate code directly (no wrapping needed)
        generated_code = compile_function(complex_function, "test_module", "test_synchronizer", test_synchronizer)

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

    def test_compile_function_no_annotations(self, test_synchronizer, no_annotation_function):
        """Test compile_function with no type annotations"""
        # Generate code directly (no wrapping needed)
        generated_code = compile_function(no_annotation_function, "test_module", "test_synchronizer", test_synchronizer)

        # Verify the generated code compiles
        compile(generated_code, "<string>", "exec")

        # Verify parameters without annotations are handled in aio method
        assert "async def aio(self, x, y = 42)" in generated_code
        # __call__ is now generated with explicit signature
        # No return type annotation since there wasn't one in the original

    def test_compile_function_template_pattern(self, test_synchronizer, simple_function):
        """Test that the generated code follows the template pattern exactly"""
        # Generate code directly (no wrapping needed)
        generated_code = compile_function(simple_function, "test_module", "test_synchronizer", test_synchronizer)

        # Check that the generated code contains all expected template elements
        template_elements = [
            "class _",
            "def __call__(self",
            "async def aio(self",
            "_run_function_sync",
            "_run_function_async",  # aio() should use _run_function_async
            "@replace_with",
        ]

        for element in template_elements:
            assert element in generated_code, f"Generated code should contain '{element}'"

        # Verify the structure - class definition and replace_with decorator
        lines = generated_code.split("\n")
        class_line = None
        for i, line in enumerate(lines):
            if line.startswith("class _"):
                class_line = i
                break

        assert class_line is not None, "Should have a class definition"

    def test_compile_function_multiple_functions(self, test_synchronizer, simple_function, complex_function):
        """Test compile_function with multiple wrapped functions"""
        # Both functions should generate valid code independently
        for func in [simple_function, complex_function]:
            generated_code = compile_function(func, "test_module", "test_synchronizer", test_synchronizer)

            # Should compile without errors
            compile(generated_code, "<string>", "exec")

            # Should contain the template pattern
            assert "class _" in generated_code
            assert "def __call__(self" in generated_code
            assert "impl_function = " in generated_code
            assert "async def aio(" in generated_code
            assert "@replace_with" in generated_code

    def test_compile_function_generic_types(self, test_synchronizer, generic_types_function, simple_function):
        """Test compile_function with generic type arguments like list[str], dict[str, int]"""
        # Generate code directly (no wrapping needed)
        generated_code = compile_function(generic_types_function, "test_module", "test_synchronizer", test_synchronizer)

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
        assert "def __call__(self" in generated_code
        assert f"impl_function = {simple_function.__module__}." in generated_code
        assert "async def aio(self" in generated_code
        assert "@replace_with" in generated_code


class TestAsyncGenerators:
    """Tests for async generator function compilation."""

    @pytest.fixture
    def async_generator_function(self):
        """Async generator function"""

        async def func(items: List[str]) -> typing.AsyncGenerator[str, None]:
            for item in items:
                await asyncio.sleep(0.01)
                yield f"processed: {item}"

        return func

    def test_compile_function_async_generator(self, test_synchronizer, async_generator_function):
        """Test compile_function with async generator function"""
        # Generate code directly (no wrapping needed)
        generated_code = compile_function(
            async_generator_function, "test_module", "test_synchronizer", test_synchronizer
        )

        # Verify the generated code compiles
        compile(generated_code, "<string>", "exec")

        # Verify it uses generator methods instead of function methods
        assert "_run_generator_sync" in generated_code
        assert "_run_generator_async" in generated_code
        assert "_run_function_sync" not in generated_code

        # Verify it generates inline helper functions for generators with send() support
        assert "async def _wrap_async_gen" in generated_code  # Async helper
        assert "def _wrap_async_gen" in generated_code  # Sync helper (note: both contain this string)
        assert "_wrapped.asend(_sent)" in generated_code  # Async helper uses asend() for two-way generators
        assert "_wrapped.send(_sent)" in generated_code  # Sync helper uses send() for two-way generators
        assert "_run_generator_async(_gen)" in generated_code
        assert "_run_generator_sync(_gen)" in generated_code
        assert "_sent = yield _item" in generated_code  # Helpers capture sent values
        assert "gen = impl_function" in generated_code
        # Methods iterate over helpers (can't return generators from async functions)
        assert "yield from self._wrap_async_gen" in generated_code  # Sync uses yield from
        assert "await _wrapped.asend(_sent)" in generated_code  # Async uses asend() to forward send values

        # Verify return type annotations for generators
        assert "typing.Generator[str" in generated_code  # Sync version returns Generator
        assert "typing.AsyncGenerator[str" in generated_code  # Async version returns AsyncGenerator

        # Verify parameter types are preserved
        assert "items: list" in generated_code

    def test_compile_function_async_generator_template_pattern(self, test_synchronizer, async_generator_function):
        """Test that async generator functions follow the template pattern"""
        # Generate code directly (no wrapping needed)
        generated_code = compile_function(
            async_generator_function, "test_module", "test_synchronizer", test_synchronizer
        )

        # Check that the generated code contains all expected template elements
        template_elements = [
            "class _",
            "def __call__(self",
            "async def aio(self",
            "@replace_with",
        ]

        for element in template_elements:
            assert element in generated_code, f"Generated code should contain '{element}'"

        # Verify the structure is correct for generators with send() support
        assert "gen = impl_function(" in generated_code
        # With send() support, we use "await _wrapped.asend(_sent)" instead of "async for"
        assert "_sent = yield _item" in generated_code
        assert "await _wrapped.asend(_sent)" in generated_code

    def test_compile_async_generator_with_wrapped_type_quoting(self, test_synchronizer):
        """Test that async generators with wrapped types quote the entire return type annotation.

        When a generator yields wrapped types (e.g., AsyncGenerator[Person, None]),
        the entire return type should be quoted as a string for forward reference safety,
        not just individual parts within the generic.

        We want: -> "typing.Generator[Person, None, None]"
        Not: -> typing.Generator["Person", None, None]
        """

        # Create a wrapped class
        class Person:
            def __init__(self, name: str):
                self.name = name

        # Register the wrapped class
        test_synchronizer[Person] = ("test_module", "Person")

        # Create an async generator that yields the wrapped type
        async def stream_people(count: int) -> typing.AsyncIterator[Person]:
            """Stream people instances."""
            for i in range(count):
                yield Person(f"Person {i}")

        # Generate code
        generated_code = compile_function(stream_people, "test_module", "test_synchronizer", test_synchronizer)

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
        assert (
            'Generator["Person"' not in generated_code
        ), "Should not quote individual type arguments within the generic"
        assert (
            'AsyncGenerator["Person"' not in generated_code
        ), "Should not quote individual type arguments within the generic"

    def test_compile_async_generator_with_nested_wrapped_type_quoting(self, test_synchronizer):
        """Test that async generators with nested wrapped types (e.g., list[Person]) quote the entire return type."""

        # Create a wrapped class
        class Person:
            def __init__(self, name: str):
                self.name = name

        # Register the wrapped class
        test_synchronizer[Person] = ("test_module", "Person")

        # Create an async generator that yields lists of the wrapped type
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

        # Generate code
        generated_code = compile_function(stream_person_batches, "test_module", "test_synchronizer", test_synchronizer)

        # Verify the generated code compiles
        compile(generated_code, "<string>", "exec")

        # The entire return type should be quoted because it contains wrapped types
        assert (
            ' -> "typing.Generator[list[Person], None, None]"' in generated_code
        ), "Sync version should quote entire Generator type when yield type contains wrapped types"
        assert (
            ' -> "typing.AsyncGenerator[list[Person]]"' in generated_code
        ), "Async version should quote entire AsyncGenerator type when yield type contains wrapped types"


class TestSyncFunctions:
    """Tests for synchronous (non-async) function compilation."""

    def test_compile_sync_function_basic(self, test_synchronizer):
        """Test compiling a basic synchronous function without type translation."""

        def simple_add(a: int, b: int) -> int:
            return a + b

        code = compile_function(simple_add, "test_module", "test_synchronizer", test_synchronizer)

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

    def test_compile_sync_function_with_wrapped_arg(self, test_synchronizer):
        """Test compiling a synchronous function that takes a wrapped type."""

        class Person:
            def __init__(self, name: str):
                self.name = name

        # Register the wrapped class
        test_synchronizer[Person] = ("test_module", "Person")

        def greet(person: Person) -> str:
            return f"Hello, {person.name}"

        code = compile_function(greet, "test_module", "test_synchronizer", test_synchronizer)

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

    def test_compile_sync_function_with_wrapped_return(self, test_synchronizer):
        """Test compiling a synchronous function that returns a wrapped type."""

        class Person:
            def __init__(self, name: str):
                self.name = name

        # Register the wrapped class
        test_synchronizer[Person] = ("test_module", "Person")

        def create_person(name: str) -> Person:
            return Person(name)

        code = compile_function(create_person, "test_module", "test_synchronizer", test_synchronizer)

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

    def test_compile_sync_function_with_list_wrapped_return(self, test_synchronizer):
        """Test compiling a synchronous function that returns a list of wrapped types."""

        class Person:
            def __init__(self, name: str):
                self.name = name

        # Register the wrapped class
        test_synchronizer[Person] = ("test_module", "Person")

        def create_people(names: list[str]) -> list[Person]:
            return [Person(name) for name in names]

        code = compile_function(create_people, "test_module", "test_synchronizer", test_synchronizer)

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

    def test_compile_sync_function_no_annotations(self, test_synchronizer):
        """Test compiling a synchronous function without type annotations."""

        def no_types(x, y):
            return x + y

        code = compile_function(no_types, "test_module", "test_synchronizer", test_synchronizer)

        # Verify generated code compiles
        compile(code, "<string>", "exec")

        # Check that it calls impl_function directly
        assert "return impl_function(x, y)" in code
        assert "_run_function_sync" not in code

    def test_compile_sync_function_with_default_args(self, test_synchronizer):
        """Test compiling a synchronous function with default arguments."""

        def with_defaults(a: int, b: int = 10, c: str = "hello") -> str:
            return f"{a}, {b}, {c}"

        code = compile_function(with_defaults, "test_module", "test_synchronizer", test_synchronizer)

        # Verify generated code compiles
        compile(code, "<string>", "exec")

        # Check that default values are preserved
        assert "b: int = 10" in code
        assert "c: str = 'hello'" in code

        # Check that it calls impl_function directly
        assert "return impl_function(a, b, c)" in code
