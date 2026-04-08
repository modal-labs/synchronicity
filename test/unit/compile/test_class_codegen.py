import asyncio
import pytest
import typing
from typing import Dict, List, Optional

from synchronicity.codegen.compile import compile_class, compile_module


# Test fixtures
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
def test_compile_class_basic(simple_class):
    """Test basic class compilation"""

    synchronized_types = {simple_class: ("test_module", "TestClass")}
    # Generate code
    generated_code = compile_class(simple_class, "test_module", synchronized_types)

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


def test_compile_class_method_descriptors(simple_class):
    """Test that method descriptors are properly generated"""

    synchronized_types = {simple_class: ("test_module", "TestClass")}
    generated_code = compile_class(simple_class, "test_module", synchronized_types)
    print(generated_code)
    # Verify method wrapper classes are generated
    assert "@wrapped_method(__add_to_value_aio)" in generated_code
    assert "async def __add_to_value_aio(self, amount: int) -> int" in generated_code
    assert "def add_to_value(self, amount: int) -> int" in generated_code


def test_compile_class_complex_types(complex_class):
    """Test class compilation with complex type annotations"""

    synchronized_types = {complex_class: ("test_module", "ComplexClass")}
    generated_code = compile_class(complex_class, "test_module", synchronized_types)

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


def test_compile_class_async_generators(async_generator_class):
    """Test class compilation with async generator methods"""

    synchronized_types = {async_generator_class: ("test_module", "AsyncGeneratorClass")}
    generated_code = compile_class(async_generator_class, "test_module", synchronized_types)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify async generator methods use generator runtime methods with inline helpers
    assert "_run_generator_sync" in generated_code
    assert "_run_generator_async" in generated_code
    # With send() support, helpers use asend()/_sent pattern
    assert "_sent = yield _item" in generated_code
    assert "await _wrapped.asend(_sent)" in generated_code
    assert "@staticmethod" in generated_code  # Helpers are static methods


def test_compile_class_mixed_methods(mixed_class):
    """Test class compilation with mixed method types"""

    synchronized_types = {mixed_class: ("test_module", "MixedClass")}
    generated_code = compile_class(mixed_class, "test_module", synchronized_types)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Verify async methods are wrapped with the new decorator pattern
    assert "@wrapped_method(" in generated_code
    assert "def process_sync(self" in generated_code
    assert "def process_generator(self" in generated_code

    # Verify sync methods are not wrapped (they don't start with async)
    # In our implementation, we only wrap async methods, so sync_method should not be wrapped
    # But it should still be accessible through __getattr__


def test_compile_class_type_annotations_preserved(simple_class):
    """Test that method type annotations are preserved"""

    synchronized_types = {simple_class: ("test_module", "TestClass")}
    generated_code = compile_class(simple_class, "test_module", synchronized_types)

    # Verify type annotations are preserved
    assert "new_value: int" in generated_code
    assert "amount: int" in generated_code
    assert "-> int" in generated_code
    assert "-> None" in generated_code


def test_compile_class_impl_instance_access(simple_class):
    """Test that the generated class provides access to the original instance"""

    synchronized_types = {simple_class: ("test_module", "TestClass")}
    generated_code = compile_class(simple_class, "test_module", synchronized_types)

    # Verify original instance is created and accessible
    # Should reference the actual module where the class is defined
    assert f"self._impl_instance = {simple_class.__module__}.{simple_class.__name__}(" in generated_code
    # Verify that the generated class has the expected structure
    assert f"class {simple_class.__name__}:" in generated_code
    assert "_synchronizer._run_function_async" in generated_code


def test_compile_class_multiple_classes(simple_class, complex_class):
    """Test compilation of multiple classes"""

    synchronized_types = {
        simple_class: ("test_module", "TestClass"),
        complex_class: ("test_module", "ComplexClass"),
    }
    # Should have 2 wrapped classes
    assert len(synchronized_types) == 2

    # Each should generate valid code
    for cls, (target_module, target_name) in synchronized_types.items():
        generated_code = compile_class(cls, "test_module", synchronized_types)

        # Should compile without errors
        compile(generated_code, "<string>", "exec")

        # Should contain the class wrapper pattern
        assert f"class {cls.__name__}:" in generated_code
        assert "_impl_instance" in generated_code
        # __getattr__ no longer used


def test_compile_class_no_methods():
    """Test compilation of a class with no async methods"""

    class EmptyClass:
        def __init__(self, value: int):
            self.value = value

        def sync_method(self) -> int:
            return self.value

    # Register the class
    synchronized_types = {EmptyClass: ("test_module", "EmptyClass")}

    generated_code = compile_class(EmptyClass, "test_module", synchronized_types)

    # Should still generate a valid wrapper class
    compile(generated_code, "<string>", "exec")
    assert f"class {EmptyClass.__name__}:" in generated_code
    assert "_impl_instance" in generated_code
    # Should not have any method wrapper assignments since no async methods


def test_compile_class_method_with_varargs():
    """Test compiling a class with methods that have varargs and keyword-only parameters."""

    class VarArgsClass:
        async def method_with_varargs(self, a: int, *args: str, b, **kwargs: float) -> str:
            return "result"

        async def method_with_posonly(self, x, y, /, z, w=10) -> int:
            return 42

    synchronized_types = {VarArgsClass: ("test_module", "VarArgsClass")}

    generated_code = compile_class(VarArgsClass, "test_module", synchronized_types)
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


def test_compile_module_multiple_classes_separation(simple_class, complex_class):
    """Test that multiple classes in a module are separated by blank lines."""
    from synchronicity.module import Module

    # Create a real Module
    test_module = Module("test_module")

    # Register classes directly in the global registry
    test_module.wrap_class(simple_class)
    test_module.wrap_class(complex_class)

    synchronized_types = {
        simple_class: ("test_module", "TestClass"),
        complex_class: ("test_module", "ComplexClass"),
    }

    # Compile the module
    generated_code = compile_module(test_module, synchronized_types)

    # Verify the code compiles
    compile(generated_code, "<string>", "exec")

    # Split by "class " to find all class declarations
    import re

    class_pattern = r"^class\s+\w+"
    lines = generated_code.split("\n")
    class_line_indices = [i for i, line in enumerate(lines) if re.match(class_pattern, line.strip())]

    # Verify there are at least 2 classes
    assert len(class_line_indices) >= 2, "Should have at least 2 classes"

    # Check that each class (except the first) has at least 2 newlines before it
    # (i.e., at least one blank line)
    for idx in class_line_indices[1:]:  # Skip the first class
        # Should have at least one blank line before the class
        # Check that the previous line is empty (represents blank line from 2 newlines)
        prev_line_idx = idx - 1
        assert prev_line_idx >= 0, f"Class at line {idx + 1} should have a line before it"
        assert lines[prev_line_idx].strip() == ""


def test_compile_class_constructor_signature_with_types():
    """Test that constructor signature is preserved with proper type annotations and unwrapping."""

    # Create a wrapped class to use as a parameter type
    class Node:
        def __init__(self, value: int):
            self.value = value

    # Create a class that takes a wrapped type in its constructor
    class Container:
        def __init__(self, node: Node, name: str, count: int = 5):
            self.node = node
            self.name = name
            self.count = count

    synchronized_types = {
        Node: ("test_module", "Node"),
        Container: ("test_module", "Container"),
    }

    generated_code = compile_class(Container, "test_module", synchronized_types)

    # Verify the generated code compiles
    compile(generated_code, "<string>", "exec")

    # Check that the constructor signature preserves the wrapper type (quoted forward ref in class body)
    assert 'def __init__(self, node: "Node", name: str, count: int = 5):' in generated_code

    # Check that the wrapped parameter is unwrapped before passing to impl constructor
    assert "node_impl = node._impl_instance" in generated_code

    # Check that the impl constructor call uses the unwrapped parameter
    assert f"self._impl_instance = {Container.__module__}.Container(node_impl, name, count)" in generated_code

    # Verify primitive types (name, count) are passed directly without unwrapping
    assert "name_impl" not in generated_code
    assert "count_impl" not in generated_code


def test_compile_class_with_sync_method_returning_coroutine():
    """Test that a sync method returning Coroutine is treated as async and gets proper wrapper."""
    from typing import Coroutine

    class TestClass:  # A sync method (no async def) that returns a Coroutine type
        def create_coroutine(self, x: int) -> Coroutine[None, None, str]: ...

    synchronized_types = {}
    generated_code = compile_class(TestClass, "test_module", synchronized_types)
    print(generated_code)

    assert "@wrapped_method" in generated_code
    assert "def create_coroutine(self, x: int) -> str:" in generated_code
    assert "async def __create_coroutine_aio(self, x: int) -> str:" in generated_code
    assert "_run_function_sync" in generated_code, "Should use synchronizer for sync version"
    assert "_run_function_async" in generated_code, "Should use synchronizer for async version"


def test_compile_class_with_sync_method_returning_awaitable():
    """Test that a sync method returning Awaitable is treated as async and gets proper wrapper."""
    from typing import Awaitable

    class TestClass:
        # A sync method (no async def) that returns an Awaitable type
        def create_awaitable(self, x: int) -> Awaitable[str]: ...

    synchronized_types = {}
    generated_code = compile_class(TestClass, "test_module", synchronized_types)
    print(generated_code)

    assert "@wrapped_method" in generated_code
    assert "def create_awaitable(self, x: int) -> str:" in generated_code
    assert "async def __create_awaitable_aio(self, x: int) -> str:" in generated_code
    assert "_run_function_sync" in generated_code, "Should use synchronizer for sync version"
    assert "_run_function_async" in generated_code, "Should use synchronizer for async version"


def test_compile_class_with_aiter_has_typed_iter():
    """Test that classes with __aiter__ generate properly typed __iter__ methods."""

    class AsyncIterableClass:
        def __aiter__(self) -> typing.AsyncIterator[str]: ...

    synchronized_types = {}
    generated_code = compile_class(AsyncIterableClass, "test_module", synchronized_types)
    print(generated_code)

    # __aiter__ returns AsyncIterator[str], which should be transformed to SyncOrAsyncIterator[str]
    # Both __iter__ and __aiter__ should return the same transformed type
    assert 'def __iter__(self) -> "synchronicity.types.SyncOrAsyncIterator[str]":' in generated_code
    assert 'def __aiter__(self) -> "synchronicity.types.SyncOrAsyncIterator[str]":' in generated_code


def test_compile_class_with_anext_has_typed_next():
    """Test that classes with __anext__ generate properly typed __next__ and __anext__ methods."""

    class AsyncIteratorClass:
        def __aiter__(self) -> typing.Self:
            return self

        async def __anext__(self) -> int: ...

    synchronized_types = {}
    generated_code = compile_class(AsyncIteratorClass, "test_module", synchronized_types)
    print(generated_code)

    # __anext__ returns int, both __next__ and __anext__ should return int
    assert "def __next__(self) -> int:" in generated_code
    assert "async def __anext__(self) -> int:" in generated_code
    # __aiter__ returns typing.Self in the wrapper signature
    assert 'def __iter__(self) -> "typing.Self":' in generated_code
    assert 'def __aiter__(self) -> "typing.Self":' in generated_code


def test_compile_class_preserves_typing_self_in_wrapper_signature():
    """typing.Self in the impl must appear as typing.Self on the wrapper (not the wrapper class name)."""

    class SelfMethodClass:
        def accept(self, s: typing.Self) -> typing.Self:
            return self

    synchronized_types = {SelfMethodClass: ("test_module", "SelfMethodClass")}
    generated_code = compile_class(SelfMethodClass, "test_module", synchronized_types)

    assert 'def accept(self, s: typing.Self) -> "typing.Self":' in generated_code
    assert "typing.cast(typing.Self, self._from_impl(result))" in generated_code
    assert "s_impl = s._impl_instance" in generated_code


def test_compile_class_aiter_signature_variations():
    """Test __iter__ and __aiter__ signature generation with various annotation styles."""
    import collections.abc

    # Case 1: Sync __aiter__ with annotation
    class SyncWithAnnotation:
        def __aiter__(self) -> typing.AsyncIterator[str]: ...

    code = compile_class(SyncWithAnnotation, "test_module", {})
    assert 'def __iter__(self) -> "synchronicity.types.SyncOrAsyncIterator[str]":' in code
    assert 'def __aiter__(self) -> "synchronicity.types.SyncOrAsyncIterator[str]":' in code

    # Case 2: Sync __aiter__ without annotation
    class SyncWithoutAnnotation:
        def __aiter__(self): ...

    code = compile_class(SyncWithoutAnnotation, "test_module", {})
    assert "def __iter__(self):" in code
    assert "def __aiter__(self):" in code
    # Should not have " -> :" which would be invalid syntax
    assert " -> :" not in code

    # Case 3: Async __aiter__ with annotation
    class AsyncWithAnnotation:
        async def __aiter__(self) -> collections.abc.AsyncIterator[int]: ...

    code = compile_class(AsyncWithAnnotation, "test_module", {})
    assert 'def __iter__(self) -> "synchronicity.types.SyncOrAsyncIterator[int]":' in code
    assert 'def __aiter__(self) -> "synchronicity.types.SyncOrAsyncIterator[int]":' in code

    # Case 4: Async __aiter__ without annotation
    # Gets normalized to Awaitable[Any], so returns Any
    class AsyncWithoutAnnotation:
        async def __aiter__(self): ...

    code = compile_class(AsyncWithoutAnnotation, "test_module", {})
    assert "def __iter__(self) -> typing.Any:" in code
    assert "def __aiter__(self) -> typing.Any:" in code

    # Case 5: Async __aiter__ with AsyncGenerator annotation
    # AsyncGenerator should be converted to Generator for sync __iter__, preserved for async __aiter__
    class AsyncWithGenerator:
        async def __aiter__(self) -> typing.AsyncGenerator[float, None]: ...

    code = compile_class(AsyncWithGenerator, "test_module", {})
    # __iter__ (sync) should use Generator
    assert 'def __iter__(self) -> "typing.Generator[float, None, None]":' in code
    # __aiter__ should preserve AsyncGenerator (as a regular method, not async def)
    assert 'def __aiter__(self) -> "typing.AsyncGenerator[float, None]":' in code

    # Case 6: Verify AsyncIterator transforms to SyncOrAsyncIterator (dual-mode, no conversion needed)
    class AsyncIterType:
        def __aiter__(self) -> typing.AsyncIterator[bool]: ...

    code = compile_class(AsyncIterType, "test_module", {})
    # Both __iter__ and __aiter__ use SyncOrAsyncIterator (which works in both contexts)
    assert 'def __iter__(self) -> "synchronicity.types.SyncOrAsyncIterator[bool]":' in code
    assert 'def __aiter__(self) -> "synchronicity.types.SyncOrAsyncIterator[bool]":' in code


def test_compile_class_without_explicit_init():
    """Test that classes without explicit __init__ generate wrapper with empty __init__ signature."""

    class NoInit:
        async def method(self) -> int:
            return 42

    synchronized_types = {}
    generated_code = compile_class(NoInit, "test_module", synchronized_types)
    print(generated_code)

    # Should have __init__ with empty signature (no *args, **kwargs)
    assert "def __init__(self):" in generated_code
    # Should NOT have *args, **kwargs
    assert "def __init__(self, *args, **kwargs):" not in generated_code
    # Should call impl with no arguments
    assert "test.unit.compile.test_class_codegen.NoInit()" in generated_code
