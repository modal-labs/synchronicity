import asyncio
import pytest
import typing
from typing import Dict, List, Optional

from synchronicity2.compile import compile_class
from synchronicity2.synchronizer import Library


# Test fixtures
@pytest.fixture
def test_library():
    """Create a test library for testing"""
    return Library("test_library")


@pytest.fixture
def simple_class():
    """Simple class with basic async methods"""

    class TestClass:
        def __init__(self, value: int):
            self.value = value

        async def get_value(self) -> int:
            await asyncio.sleep(0.01)
            return self.value

        async def set_value(self, new_value: int) -> None:
            await asyncio.sleep(0.01)
            self.value = new_value

        async def add_to_value(self, amount: int) -> int:
            await asyncio.sleep(0.01)
            self.value += amount
            return self.value

    return TestClass


@pytest.fixture
def complex_class():
    """Class with complex type annotations"""

    class ComplexClass:
        def __init__(self, data: List[str]):
            self.data = data

        async def process_data(self, config: Dict[str, int], optional_filter: Optional[str] = None) -> List[str]:
            await asyncio.sleep(0.01)
            result = []
            for item in self.data:
                if optional_filter is None or optional_filter in item:
                    result.append(f"processed_{item}")
            return result

        async def get_data_length(self) -> int:
            await asyncio.sleep(0.01)
            return len(self.data)

    return ComplexClass


@pytest.fixture
def async_generator_class():
    """Class with async generator methods"""

    class AsyncGeneratorClass:
        def __init__(self, items: List[str]):
            self.items = items

        async def stream_items(self) -> typing.AsyncGenerator[str, None]:
            for item in self.items:
                await asyncio.sleep(0.01)
                yield item

        async def stream_with_filter(self, prefix: str) -> typing.AsyncGenerator[str, None]:
            for item in self.items:
                if item.startswith(prefix):
                    await asyncio.sleep(0.01)
                    yield item

    return AsyncGeneratorClass


@pytest.fixture
def mixed_class():
    """Class with mixed method types"""

    class MixedClass:
        def __init__(self, data: List[str]):
            self.data = data

        async def process_sync(self, item: str) -> str:
            await asyncio.sleep(0.01)
            return f"processed_{item}"

        async def process_generator(self) -> typing.AsyncGenerator[str, None]:
            for item in self.data:
                await asyncio.sleep(0.01)
                yield f"generated_{item}"

        def sync_method(self, item: str) -> str:
            # This should be ignored by the wrapper since it's not async
            return f"sync_{item}"

    return MixedClass


# Test basic class compilation
def test_compile_class_basic(test_library, simple_class):
    """Test basic class compilation"""
    test_library.wrap(target_module="test_module")(simple_class)

    # Get the wrapped class
    wrapped_class = None
    target_module = None
    for cls, (module, name) in test_library._wrapped.items():
        if cls.__name__ == simple_class.__name__:
            wrapped_class = cls
            target_module = module
            break

    assert wrapped_class is not None, "Class should be wrapped"

    # Generate code
    generated_code = compile_class(wrapped_class, target_module, test_library._synchronizer_name)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify it contains expected elements
    assert f"class {simple_class.__name__}:" in generated_code
    assert "_impl_instance" in generated_code
    assert "@wrapped_method(" in generated_code
    assert "def get_value(self" in generated_code
    assert "def set_value(self" in generated_code
    assert "def add_to_value(self" in generated_code
    assert "impl_function = " in generated_code


def test_compile_class_method_descriptors(test_library, simple_class):
    """Test that method descriptors are properly generated"""
    test_library.wrap(target_module="test_module")(simple_class)

    # Get the wrapped class
    wrapped_class = None
    target_module = None
    for cls, (module, name) in test_library._wrapped.items():
        if cls.__name__ == simple_class.__name__:
            wrapped_class = cls
            target_module = module
            break

    generated_code = compile_class(wrapped_class, target_module, test_library._synchronizer_name)

    # Verify method wrapper classes are generated
    assert "TestClass_get_value" in generated_code
    assert "async def aio(self" in generated_code
    assert "def __call__(self" in generated_code
    # Method wrapper pattern has changed
    assert "def __call__(self" in generated_code
    assert "async def aio(self" in generated_code


def test_compile_class_complex_types(test_library, complex_class):
    """Test class compilation with complex type annotations"""
    test_library.wrap(target_module="test_module")(complex_class)

    # Get the wrapped class
    wrapped_class = None
    target_module = None
    for cls, (module, name) in test_library._wrapped.items():
        if cls.__name__ == complex_class.__name__:
            wrapped_class = cls
            target_module = module
            break

    generated_code = compile_class(wrapped_class, target_module, test_library._synchronizer_name)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify complex type annotations are preserved (now using lowercase types)
    assert "config: dict[str, int]" in generated_code
    assert ("optional_filter: typing.Union[str, None]" in generated_code or
            "optional_filter: str | None" in generated_code or
            "optional_filter: typing.Optional[str]" in generated_code)
    assert "-> list[str]" in generated_code


def test_compile_class_async_generators(test_library, async_generator_class):
    """Test class compilation with async generator methods"""
    test_library.wrap(target_module="test_module")(async_generator_class)

    # Get the wrapped class
    wrapped_class = None
    target_module = None
    for cls, (module, name) in test_library._wrapped.items():
        if cls.__name__ == async_generator_class.__name__:
            wrapped_class = cls
            target_module = module
            break

    generated_code = compile_class(wrapped_class, target_module, test_library._synchronizer_name)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify async generator methods use generator runtime methods
    assert "_run_generator_sync" in generated_code
    assert "_run_generator_async" in generated_code
    assert "yield from" in generated_code
    assert "async for item in" in generated_code


def test_compile_class_mixed_methods(test_library, mixed_class):
    """Test class compilation with mixed method types"""
    test_library.wrap(target_module="test_module")(mixed_class)

    # Get the wrapped class
    wrapped_class = None
    target_module = None
    for cls, (module, name) in test_library._wrapped.items():
        if cls.__name__ == mixed_class.__name__:
            wrapped_class = cls
            target_module = module
            break

    generated_code = compile_class(wrapped_class, target_module, test_library._synchronizer_name)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify async methods are wrapped with the new decorator pattern
    assert "@wrapped_method(" in generated_code
    assert "def process_sync(self" in generated_code
    assert "def process_generator(self" in generated_code

    # Verify sync methods are not wrapped (they don't start with async)
    # In our implementation, we only wrap async methods, so sync_method should not be wrapped
    # But it should still be accessible through __getattr__


def test_compile_class_type_annotations_preserved(test_library, simple_class):
    """Test that method type annotations are preserved"""
    test_library.wrap(target_module="test_module")(simple_class)

    # Get the wrapped class
    wrapped_class = None
    target_module = None
    for cls, (module, name) in test_library._wrapped.items():
        if cls.__name__ == simple_class.__name__:
            wrapped_class = cls
            target_module = module
            break

    generated_code = compile_class(wrapped_class, target_module, test_library._synchronizer_name)

    # Verify type annotations are preserved
    assert "new_value: int" in generated_code
    assert "amount: int" in generated_code
    assert "-> int" in generated_code
    assert "-> None" in generated_code


def test_compile_class_instance_binding(test_library, simple_class):
    """Test that the generated code properly handles instance binding"""
    test_library.wrap(target_module="test_module")(simple_class)

    # Get the wrapped class
    wrapped_class = None
    target_module = None
    for cls, (module, name) in test_library._wrapped.items():
        if cls.__name__ == simple_class.__name__:
            wrapped_class = cls
            target_module = module
            break

    generated_code = compile_class(wrapped_class, target_module, test_library._synchronizer_name)

    # Verify method wrapper classes are present (new decorator pattern)
    assert "class TestClass_" in generated_code  # Method wrapper classes
    assert "def __call__(self" in generated_code
    assert "async def aio(self" in generated_code
    assert "@wrapped_method(" in generated_code
    assert "impl_function = " in generated_code  # Method implementation reference


def test_compile_class_impl_instance_access(test_library, simple_class):
    """Test that the generated class provides access to the original instance"""
    test_library.wrap(target_module="test_module")(simple_class)

    # Get the wrapped class
    wrapped_class = None
    target_module = None
    for cls, (module, name) in test_library._wrapped.items():
        if cls.__name__ == simple_class.__name__:
            wrapped_class = cls
            target_module = module
            break

    generated_code = compile_class(wrapped_class, target_module, test_library._synchronizer_name)

    # Verify original instance is created and accessible
    assert "self._impl_instance = test_module.TestClass(" in generated_code
    # Verify that the generated class has the expected structure
    assert f"class {simple_class.__name__}:" in generated_code
    assert "_synchronizer = get_synchronizer(" in generated_code


def test_compile_class_multiple_classes(test_library, simple_class, complex_class):
    """Test compilation of multiple classes"""
    test_library.wrap(target_module="test_module")(simple_class)
    test_library.wrap(target_module="test_module")(complex_class)

    # Should have 2 wrapped classes
    assert len(test_library._wrapped) == 2

    # Each should generate valid code
    for cls, (target_module, target_name) in test_library._wrapped.items():
        generated_code = compile_class(cls, target_module, test_library._synchronizer_name)

        # Should compile without errors
        compile(generated_code, "<string>", "exec")

        # Should contain the class wrapper pattern
        assert f"class {cls.__name__}:" in generated_code
        assert "_impl_instance" in generated_code
        # __getattr__ no longer used


def test_compile_class_no_methods():
    """Test compilation of a class with no async methods"""
    test_library = Library("test_library")

    class EmptyClass:
        def __init__(self, value: int):
            self.value = value

        def sync_method(self) -> int:
            return self.value

    test_library.wrap(target_module="test_module")(EmptyClass)

    # Get the wrapped class
    wrapped_class = None
    target_module = None
    for cls, (module, name) in test_library._wrapped.items():
        if cls.__name__ == EmptyClass.__name__:
            wrapped_class = cls
            target_module = module
            break

    generated_code = compile_class(wrapped_class, target_module, test_library._synchronizer_name)

    # Should still generate a valid wrapper class
    compile(generated_code, "<string>", "exec")
    assert f"class {EmptyClass.__name__}:" in generated_code
    assert "_impl_instance" in generated_code
    # Should not have any method wrapper assignments since no async methods
