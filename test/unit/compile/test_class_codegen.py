import asyncio
import pytest
import typing
from typing import Dict, List, Optional

from synchronicity.codegen.compile import compile_class


# Test fixtures
@pytest.fixture
def test_synchronizer():
    """Empty synchronized_types dict for testing (replaces Synchronizer._wrapped)."""
    return {}


@pytest.fixture
def simple_class(test_synchronizer):
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

    # Register the class in synchronized_types
    test_synchronizer[TestClass] = ("test_module", "TestClass")
    return TestClass


@pytest.fixture
def complex_class(test_synchronizer):
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

    # Register the class in synchronized_types
    test_synchronizer[ComplexClass] = ("test_module", "ComplexClass")
    return ComplexClass


@pytest.fixture
def async_generator_class(test_synchronizer):
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

    # Register the class in synchronized_types
    test_synchronizer[AsyncGeneratorClass] = ("test_module", "AsyncGeneratorClass")
    return AsyncGeneratorClass


@pytest.fixture
def mixed_class(test_synchronizer):
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

    # Register the class in synchronized_types
    test_synchronizer[MixedClass] = ("test_module", "MixedClass")
    return MixedClass


# Test basic class compilation
def test_compile_class_basic(test_synchronizer, simple_class):
    """Test basic class compilation"""

    # Generate code
    generated_code = compile_class(simple_class, "test_module", "test_synchronizer", test_synchronizer)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify it contains expected elements
    assert f"class {simple_class.__name__}:" in generated_code
    assert "_impl_instance" in generated_code
    assert "@wrapped_method(" in generated_code
    assert "def get_value(self" in generated_code
    assert "def set_value(self" in generated_code
    assert "def add_to_value(self" in generated_code
    assert "impl_method = " in generated_code


def test_compile_class_method_descriptors(test_synchronizer, simple_class):
    """Test that method descriptors are properly generated"""

    generated_code = compile_class(simple_class, "test_module", "test_synchronizer", test_synchronizer)

    # Verify method wrapper classes are generated
    assert "TestClass_get_value" in generated_code
    assert "async def aio(self" in generated_code
    assert "def __call__(self" in generated_code
    # Method wrapper pattern has changed
    assert "def __call__(self" in generated_code
    assert "async def aio(self" in generated_code


def test_compile_class_complex_types(test_synchronizer, complex_class):
    """Test class compilation with complex type annotations"""

    generated_code = compile_class(complex_class, "test_module", "test_synchronizer", test_synchronizer)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify complex type annotations are preserved (now using lowercase types)
    assert "config: dict[str, int]" in generated_code
    assert (
        "optional_filter: typing.Union[str, None]" in generated_code
        or "optional_filter: str | None" in generated_code
        or "optional_filter: typing.Optional[str]" in generated_code
    )
    assert "-> list[str]" in generated_code


def test_compile_class_async_generators(test_synchronizer, async_generator_class):
    """Test class compilation with async generator methods"""

    generated_code = compile_class(async_generator_class, "test_module", "test_synchronizer", test_synchronizer)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify async generator methods use generator runtime methods with inline helpers
    assert "_run_generator_sync" in generated_code
    assert "_run_generator_async" in generated_code
    # With send() support, helpers use asend()/_sent pattern
    assert "_sent = yield _item" in generated_code
    assert "await _wrapped.asend(_sent)" in generated_code
    assert "@staticmethod" in generated_code  # Helpers are static methods


def test_compile_class_mixed_methods(test_synchronizer, mixed_class):
    """Test class compilation with mixed method types"""

    generated_code = compile_class(mixed_class, "test_module", "test_synchronizer", test_synchronizer)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify async methods are wrapped with the new decorator pattern
    assert "@wrapped_method(" in generated_code
    assert "def process_sync(self" in generated_code
    assert "def process_generator(self" in generated_code

    # Verify sync methods are not wrapped (they don't start with async)
    # In our implementation, we only wrap async methods, so sync_method should not be wrapped
    # But it should still be accessible through __getattr__


def test_compile_class_type_annotations_preserved(test_synchronizer, simple_class):
    """Test that method type annotations are preserved"""

    generated_code = compile_class(simple_class, "test_module", "test_synchronizer", test_synchronizer)

    # Verify type annotations are preserved
    assert "new_value: int" in generated_code
    assert "amount: int" in generated_code
    assert "-> int" in generated_code
    assert "-> None" in generated_code


def test_compile_class_instance_binding(test_synchronizer, simple_class):
    """Test that the generated code properly handles instance binding"""

    generated_code = compile_class(simple_class, "test_module", "test_synchronizer", test_synchronizer)

    # Verify method wrapper classes are present (new decorator pattern)
    assert "class TestClass_" in generated_code  # Method wrapper classes
    assert "def __call__(self" in generated_code
    assert "async def aio(self" in generated_code
    assert "@wrapped_method(" in generated_code
    assert "impl_method = " in generated_code  # Method implementation reference


def test_compile_class_impl_instance_access(test_synchronizer, simple_class):
    """Test that the generated class provides access to the original instance"""

    generated_code = compile_class(simple_class, "test_module", "test_synchronizer", test_synchronizer)

    # Verify original instance is created and accessible
    # Should reference the actual module where the class is defined
    assert f"self._impl_instance = {simple_class.__module__}.{simple_class.__name__}(" in generated_code
    # Verify that the generated class has the expected structure
    assert f"class {simple_class.__name__}:" in generated_code
    assert "_synchronizer = get_synchronizer(" in generated_code


def test_compile_class_multiple_classes(test_synchronizer, simple_class, complex_class):
    """Test compilation of multiple classes"""

    # Should have 2 wrapped classes
    assert len(test_synchronizer) == 2

    # Each should generate valid code
    for cls, (target_module, target_name) in test_synchronizer.items():
        generated_code = compile_class(cls, "test_module", "test_synchronizer", test_synchronizer)

        # Should compile without errors
        compile(generated_code, "<string>", "exec")

        # Should contain the class wrapper pattern
        assert f"class {cls.__name__}:" in generated_code
        assert "_impl_instance" in generated_code
        # __getattr__ no longer used


def test_compile_class_no_methods():
    """Test compilation of a class with no async methods"""
    test_synchronizer = {}

    class EmptyClass:
        def __init__(self, value: int):
            self.value = value

        def sync_method(self) -> int:
            return self.value

    # Register the class
    test_synchronizer[EmptyClass] = ("test_module", "EmptyClass")

    generated_code = compile_class(EmptyClass, "test_module", "test_synchronizer", test_synchronizer)

    # Should still generate a valid wrapper class
    compile(generated_code, "<string>", "exec")
    assert f"class {EmptyClass.__name__}:" in generated_code
    assert "_impl_instance" in generated_code
    # Should not have any method wrapper assignments since no async methods


def test_compile_class_method_with_varargs(test_synchronizer):
    """Test compiling a class with methods that have varargs and keyword-only parameters."""

    class VarArgsClass:
        async def method_with_varargs(self, a: int, *args: str, b, **kwargs: float) -> str:
            return "result"

        async def method_with_posonly(self, x, y, /, z, w=10) -> int:
            return 42

    test_synchronizer[VarArgsClass] = ("test_module", "VarArgsClass")

    generated_code = compile_class(VarArgsClass, "test_module", "test_synchronizer", test_synchronizer)
    print(generated_code)
    # Check that varargs markers are preserved in method signatures
    assert "*args: str" in generated_code
    assert "**kwargs: float" in generated_code
    assert "a: int, *args: str, b, **kwargs: float" in generated_code

    # Check that positional-only markers are preserved
    assert "x, y, /" in generated_code

    # Check that the dummy method placeholder uses proper unpacking
    assert "*args" in generated_code
    assert "b=b" in generated_code
    assert "**kwargs" in generated_code

    # Verify the actual implementation methods use proper unpacking
    assert "impl_method(self._impl_instance, a, *args, b=b, **kwargs)" in generated_code
