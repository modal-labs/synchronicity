"""Unit tests for type transformers.

Tests each transformer type for:
1. Type signature formatting (wrapped_type)
2. Unwrap expressions (wrapper → impl)
3. Wrap expressions (impl → wrapper)
4. Actual execution of wrap/unwrap code
"""

import pytest

from synchronicity.codegen.type_transformer import (
    DictTransformer,
    GeneratorTransformer,
    IdentityTransformer,
    ListTransformer,
    OptionalTransformer,
    TupleTransformer,
    WrappedClassTransformer,
    create_transformer,
)


@pytest.fixture
def sync():
    """Create synchronized_types dict for testing (replaces old Synchronizer._wrapped)."""

    # Create a test class
    class TestClass:
        def __init__(self, value: int):
            self.value = value

    # Return a dict with the class registered (simulates Module.module_items())
    return {TestClass: ("test_module", "TestClass")}


@pytest.fixture
def wrapped_class(sync):
    """Get the wrapped class from the sync fixture."""
    # Extract the class from the synchronized_types dict
    return list(sync.keys())[0]


class TestIdentityTransformer:
    """Test IdentityTransformer for primitive types."""

    def test_wrapped_type_int(self, sync):
        transformer = IdentityTransformer(int)
        assert transformer.wrapped_type(sync, "test_module") == "int"

    def test_wrapped_type_str(self, sync):
        transformer = IdentityTransformer(str)
        assert transformer.wrapped_type(sync, "test_module") == "str"

    def test_unwrap_expr_returns_same(self, sync):
        transformer = IdentityTransformer(int)
        assert transformer.unwrap_expr(sync, "value") == "value"

    def test_wrap_expr_returns_same(self, sync):
        transformer = IdentityTransformer(str)
        assert transformer.wrap_expr(sync, "test_module", "value") == "value"

    def test_needs_translation_false(self, sync):
        transformer = IdentityTransformer(int)
        assert transformer.needs_translation() is False

    def test_execution_passthrough(self, sync):
        """Test that identity transformer passes values through."""
        transformer = IdentityTransformer(int)

        # Unwrap should be identity
        value = 42
        unwrap_code = f"result = {transformer.unwrap_expr(sync, 'value')}"
        exec(unwrap_code, {"value": value}, locals_dict := {})
        assert locals_dict["result"] == 42

        # Wrap should be identity
        wrap_code = f"result = {transformer.wrap_expr(sync, 'test_module', 'value')}"
        exec(wrap_code, {"value": value}, locals_dict := {})
        assert locals_dict["result"] == 42


class TestWrappedClassTransformer:
    """Test WrappedClassTransformer for wrapped classes."""

    def test_wrapped_type_local_reference(self, sync, wrapped_class):
        transformer = WrappedClassTransformer(wrapped_class)
        # When target_module matches, should return just class name
        result = transformer.wrapped_type(sync, "test_module")
        assert result == "TestClass"

    def test_wrapped_type_cross_module_reference(self, sync, wrapped_class):
        transformer = WrappedClassTransformer(wrapped_class)
        # When target_module differs, should return fully qualified name
        result = transformer.wrapped_type(sync, "other_module")
        assert result == "test_module.TestClass"

    def test_unwrap_expr(self, sync, wrapped_class):
        transformer = WrappedClassTransformer(wrapped_class)
        assert transformer.unwrap_expr(sync, "obj") == "obj._impl_instance"

    def test_wrap_expr_local(self, sync, wrapped_class):
        transformer = WrappedClassTransformer(wrapped_class)
        result = transformer.wrap_expr(sync, "test_module", "impl")
        assert result == "TestClass._from_impl(impl)"

    def test_wrap_expr_cross_module(self, sync, wrapped_class):
        transformer = WrappedClassTransformer(wrapped_class)
        result = transformer.wrap_expr(sync, "other_module", "impl")
        assert result == "test_module.TestClass._from_impl(impl)"

    def test_needs_translation_true(self, sync, wrapped_class):
        transformer = WrappedClassTransformer(wrapped_class)
        assert transformer.needs_translation() is True


class TestListTransformer:
    """Test ListTransformer for list[T] types."""

    def test_wrapped_type_primitives(self, sync):
        item_transformer = IdentityTransformer(int)
        transformer = ListTransformer(item_transformer)
        assert transformer.wrapped_type(sync, "test_module") == "list[int]"

    def test_wrapped_type_wrapped_class(self, sync, wrapped_class):
        item_transformer = WrappedClassTransformer(wrapped_class)
        transformer = ListTransformer(item_transformer)
        assert transformer.wrapped_type(sync, "test_module") == "list[TestClass]"

    def test_unwrap_expr_primitives(self, sync):
        """Primitives don't need unwrapping."""
        item_transformer = IdentityTransformer(int)
        transformer = ListTransformer(item_transformer)
        assert transformer.unwrap_expr(sync, "values") == "values"

    def test_unwrap_expr_wrapped_class(self, sync, wrapped_class):
        item_transformer = WrappedClassTransformer(wrapped_class)
        transformer = ListTransformer(item_transformer)
        result = transformer.unwrap_expr(sync, "items")
        assert result == "[x._impl_instance for x in items]"

    def test_wrap_expr_wrapped_class(self, sync, wrapped_class):
        item_transformer = WrappedClassTransformer(wrapped_class)
        transformer = ListTransformer(item_transformer)
        result = transformer.wrap_expr(sync, "test_module", "impl_items")
        assert result == "[TestClass._from_impl(x) for x in impl_items]"

    def test_needs_translation(self, sync, wrapped_class):
        # List of primitives doesn't need translation
        transformer1 = ListTransformer(IdentityTransformer(int))
        assert transformer1.needs_translation() is False

        # List of wrapped classes needs translation
        transformer2 = ListTransformer(WrappedClassTransformer(wrapped_class))
        assert transformer2.needs_translation() is True

    def test_execution_list_comprehension(self, sync):
        """Test that list comprehension unwrap code executes correctly."""

        # Create mock objects with _impl_instance
        class MockWrapper:
            def __init__(self, value):
                self._impl_instance = value

        items = [MockWrapper(1), MockWrapper(2), MockWrapper(3)]

        # Execute the unwrap expression
        unwrap_expr = "[x._impl_instance for x in items]"
        result = eval(unwrap_expr, {"items": items})

        assert result == [1, 2, 3]


class TestDictTransformer:
    """Test DictTransformer for dict[K, V] types."""

    def test_wrapped_type(self, sync, wrapped_class):
        key_transformer = IdentityTransformer(str)
        value_transformer = WrappedClassTransformer(wrapped_class)
        transformer = DictTransformer(key_transformer, value_transformer)
        assert transformer.wrapped_type(sync, "test_module") == "dict[str, TestClass]"

    def test_unwrap_expr_primitives(self, sync):
        """Dict with primitive values doesn't need unwrapping."""
        key_transformer = IdentityTransformer(str)
        value_transformer = IdentityTransformer(int)
        transformer = DictTransformer(key_transformer, value_transformer)
        assert transformer.unwrap_expr(sync, "mapping") == "mapping"

    def test_unwrap_expr_wrapped_values(self, sync, wrapped_class):
        key_transformer = IdentityTransformer(str)
        value_transformer = WrappedClassTransformer(wrapped_class)
        transformer = DictTransformer(key_transformer, value_transformer)
        result = transformer.unwrap_expr(sync, "mapping")
        assert result == "{k: v._impl_instance for k, v in mapping.items()}"

    def test_wrap_expr_wrapped_values(self, sync, wrapped_class):
        key_transformer = IdentityTransformer(str)
        value_transformer = WrappedClassTransformer(wrapped_class)
        transformer = DictTransformer(key_transformer, value_transformer)
        result = transformer.wrap_expr(sync, "test_module", "impl_mapping")
        assert result == "{k: TestClass._from_impl(v) for k, v in impl_mapping.items()}"

    def test_needs_translation(self, sync, wrapped_class):
        # Dict with primitive values doesn't need translation
        transformer1 = DictTransformer(IdentityTransformer(str), IdentityTransformer(int))
        assert transformer1.needs_translation() is False

        # Dict with wrapped values needs translation
        transformer2 = DictTransformer(IdentityTransformer(str), WrappedClassTransformer(wrapped_class))
        assert transformer2.needs_translation() is True

    def test_execution_dict_comprehension(self, sync):
        """Test that dict comprehension unwrap code executes correctly."""

        class MockWrapper:
            def __init__(self, value):
                self._impl_instance = value

        mapping = {"a": MockWrapper(1), "b": MockWrapper(2)}

        # Execute the unwrap expression
        unwrap_expr = "{k: v._impl_instance for k, v in mapping.items()}"
        result = eval(unwrap_expr, {"mapping": mapping})

        assert result == {"a": 1, "b": 2}


class TestTupleTransformer:
    """Test TupleTransformer for tuple types."""

    def test_wrapped_type_variable_length(self, sync):
        """Test tuple[T, ...] formatting."""
        item_transformer = IdentityTransformer(int)
        transformer = TupleTransformer([item_transformer])
        assert transformer.wrapped_type(sync, "test_module") == "tuple[int, ...]"

    def test_wrapped_type_fixed_size(self, sync, wrapped_class):
        """Test tuple[T1, T2] formatting."""
        transformers = [IdentityTransformer(int), WrappedClassTransformer(wrapped_class)]
        transformer = TupleTransformer(transformers)
        assert transformer.wrapped_type(sync, "test_module") == "tuple[int, TestClass]"

    def test_unwrap_expr_variable_length(self, sync, wrapped_class):
        item_transformer = WrappedClassTransformer(wrapped_class)
        transformer = TupleTransformer([item_transformer])
        result = transformer.unwrap_expr(sync, "items")
        assert result == "tuple(x._impl_instance for x in items)"

    def test_unwrap_expr_fixed_size(self, sync, wrapped_class):
        """Test fixed-size tuple unwrapping by index."""
        transformers = [IdentityTransformer(int), WrappedClassTransformer(wrapped_class)]
        transformer = TupleTransformer(transformers)
        result = transformer.unwrap_expr(sync, "items")
        assert result == "(items[0], items[1]._impl_instance)"

    def test_wrap_expr_fixed_size(self, sync, wrapped_class):
        transformers = [IdentityTransformer(int), WrappedClassTransformer(wrapped_class)]
        transformer = TupleTransformer(transformers)
        result = transformer.wrap_expr(sync, "test_module", "impl_items")
        assert result == "(impl_items[0], TestClass._from_impl(impl_items[1]))"

    def test_execution_fixed_size_tuple(self, sync):
        """Test that fixed-size tuple unwrap code executes correctly."""

        class MockWrapper:
            def __init__(self, value):
                self._impl_instance = value

        items = (42, MockWrapper(100))

        # Execute the unwrap expression
        unwrap_expr = "(items[0], items[1]._impl_instance)"
        result = eval(unwrap_expr, {"items": items})

        assert result == (42, 100)


class TestOptionalTransformer:
    """Test OptionalTransformer for Optional[T] types."""

    def test_wrapped_type(self, sync, wrapped_class):
        inner_transformer = WrappedClassTransformer(wrapped_class)
        transformer = OptionalTransformer(inner_transformer)
        assert transformer.wrapped_type(sync, "test_module") == "typing.Union[TestClass, None]"

    def test_unwrap_expr(self, sync, wrapped_class):
        inner_transformer = WrappedClassTransformer(wrapped_class)
        transformer = OptionalTransformer(inner_transformer)
        result = transformer.unwrap_expr(sync, "obj")
        assert result == "obj._impl_instance if obj is not None else None"

    def test_wrap_expr(self, sync, wrapped_class):
        inner_transformer = WrappedClassTransformer(wrapped_class)
        transformer = OptionalTransformer(inner_transformer)
        result = transformer.wrap_expr(sync, "test_module", "impl")
        assert result == "TestClass._from_impl(impl) if impl is not None else None"

    def test_needs_translation(self, sync, wrapped_class):
        # Optional primitive doesn't need translation
        transformer1 = OptionalTransformer(IdentityTransformer(int))
        assert transformer1.needs_translation() is False

        # Optional wrapped class needs translation
        transformer2 = OptionalTransformer(WrappedClassTransformer(wrapped_class))
        assert transformer2.needs_translation() is True

    def test_execution_unwrap_none(self, sync):
        """Test unwrap with None value."""
        unwrap_expr = "value._impl_instance if value is not None else None"
        result = eval(unwrap_expr, {"value": None})
        assert result is None

    def test_execution_unwrap_not_none(self, sync):
        """Test unwrap with non-None value."""

        class MockWrapper:
            def __init__(self, value):
                self._impl_instance = value

        obj = MockWrapper(42)
        unwrap_expr = "value._impl_instance if value is not None else None"
        result = eval(unwrap_expr, {"value": obj})
        assert result == 42


class TestGeneratorTransformer:
    """Test GeneratorTransformer for Generator/AsyncGenerator types."""

    def test_wrapped_type_async_generator(self, sync, wrapped_class):
        yield_transformer = WrappedClassTransformer(wrapped_class)
        transformer = GeneratorTransformer(yield_transformer, is_async=True, send_type_str="None")
        assert transformer.wrapped_type(sync, "test_module") == "typing.AsyncGenerator[TestClass, None]"

    def test_wrapped_type_async_iterator_no_send(self, sync):
        """AsyncIterator doesn't have send type."""
        yield_transformer = IdentityTransformer(int)
        transformer = GeneratorTransformer(yield_transformer, is_async=True, send_type_str=None)
        assert transformer.wrapped_type(sync, "test_module") == "typing.AsyncGenerator[int]"

    def test_wrapped_type_sync_generator(self, sync):
        yield_transformer = IdentityTransformer(str)
        transformer = GeneratorTransformer(yield_transformer, is_async=False)
        assert transformer.wrapped_type(sync, "test_module") == "typing.Generator[str, None, None]"

    def test_needs_translation(self, sync, wrapped_class):
        # Generator of primitives doesn't need translation
        transformer1 = GeneratorTransformer(IdentityTransformer(int), is_async=True)
        assert transformer1.needs_translation() is False

        # Generator of wrapped classes needs translation
        transformer2 = GeneratorTransformer(WrappedClassTransformer(wrapped_class), is_async=True)
        assert transformer2.needs_translation() is True

    def test_get_yield_wrap_expr(self, sync, wrapped_class):
        yield_transformer = WrappedClassTransformer(wrapped_class)
        transformer = GeneratorTransformer(yield_transformer, is_async=True)
        result = transformer.get_yield_wrap_expr(sync, "test_module", "item")
        assert result == "TestClass._from_impl(item)"


class TestCreateTransformer:
    """Test the create_transformer factory function."""

    def test_create_primitive(self, sync):
        transformer = create_transformer(int, sync)
        assert isinstance(transformer, IdentityTransformer)

    def test_create_wrapped_class(self, sync, wrapped_class):
        transformer = create_transformer(wrapped_class, sync)
        assert isinstance(transformer, WrappedClassTransformer)

    def test_create_list(self, sync):
        from typing import List

        transformer = create_transformer(List[int], sync)
        assert isinstance(transformer, ListTransformer)
        assert isinstance(transformer.item_transformer, IdentityTransformer)

    def test_create_dict(self, sync):
        from typing import Dict

        transformer = create_transformer(Dict[str, int], sync)
        assert isinstance(transformer, DictTransformer)

    def test_create_tuple_fixed(self, sync, wrapped_class):
        from typing import Tuple

        transformer = create_transformer(Tuple[int, wrapped_class], sync)
        assert isinstance(transformer, TupleTransformer)
        assert len(transformer.item_transformers) == 2

    def test_create_optional(self, sync, wrapped_class):
        from typing import Optional

        transformer = create_transformer(Optional[wrapped_class], sync)
        assert isinstance(transformer, OptionalTransformer)
        assert isinstance(transformer.inner_transformer, WrappedClassTransformer)

    def test_create_async_generator(self, sync):
        from typing import AsyncGenerator

        transformer = create_transformer(AsyncGenerator[str, None], sync)
        assert isinstance(transformer, GeneratorTransformer)
        assert transformer.is_async is True

    def test_nested_list_of_optional_wrapped(self, sync, wrapped_class):
        """Test nested type: list[Optional[WrappedClass]]."""
        from typing import List, Optional

        transformer = create_transformer(List[Optional[wrapped_class]], sync)
        assert isinstance(transformer, ListTransformer)
        assert isinstance(transformer.item_transformer, OptionalTransformer)
        assert isinstance(transformer.item_transformer.inner_transformer, WrappedClassTransformer)

        # Check type signature
        result = transformer.wrapped_type(sync, "test_module")
        assert result == "list[typing.Union[TestClass, None]]"

        # Check needs translation
        assert transformer.needs_translation() is True


class TestComplexNestedTypes:
    """Test complex nested type transformations."""

    def test_dict_of_list_of_wrapped(self, sync, wrapped_class):
        """Test dict[str, list[WrappedClass]]."""
        from typing import Dict, List

        transformer = create_transformer(Dict[str, List[wrapped_class]], sync)

        # Check type signature
        result = transformer.wrapped_type(sync, "test_module")
        assert result == "dict[str, list[TestClass]]"

        # Check unwrap expression
        unwrap = transformer.unwrap_expr(sync, "data")
        assert "[x._impl_instance for x in v]" in unwrap
        assert "for k, v in data.items()" in unwrap

        # Check needs translation
        assert transformer.needs_translation() is True

    def test_tuple_of_mixed_types(self, sync, wrapped_class):
        """Test tuple[int, WrappedClass, str]."""
        from typing import Tuple

        transformer = create_transformer(Tuple[int, wrapped_class, str], sync)

        # Check type signature
        result = transformer.wrapped_type(sync, "test_module")
        assert result == "tuple[int, TestClass, str]"

        # Check unwrap - should unwrap only the wrapped class at index 1
        unwrap = transformer.unwrap_expr(sync, "items")
        assert "items[0]" in unwrap
        assert "items[1]._impl_instance" in unwrap
        assert "items[2]" in unwrap

    def test_execution_nested_unwrap(self, sync):
        """Test executing nested unwrap code."""

        class MockWrapper:
            def __init__(self, value):
                self._impl_instance = value

        # Test dict[str, list[Wrapped]]
        data = {"a": [MockWrapper(1), MockWrapper(2)], "b": [MockWrapper(3)]}

        # Execute nested unwrap
        unwrap_expr = "{k: [x._impl_instance for x in v] for k, v in data.items()}"
        result = eval(unwrap_expr, {"data": data})

        assert result == {"a": [1, 2], "b": [3]}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
