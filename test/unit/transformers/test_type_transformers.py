"""Unit tests for type transformers.

Tests each transformer type for:
1. Type signature formatting (wrapped_type)
2. Unwrap expressions (wrapper → impl)
3. Wrap expressions (impl → wrapper)
4. Actual execution of wrap/unwrap code
"""

import pytest
import sys

from synchronicity2.codegen.transformer_ir import ImplQualifiedRef, WrapperRef
from synchronicity2.codegen.transformer_materialize import (
    annotation_to_transformer_ir,
    materialize_transformer_ir,
)
from synchronicity2.codegen.type_transformer import (
    AsyncGeneratorTransformer,
    AwaitableTransformer,
    CoroutineTransformer,
    DictTransformer,
    IdentityStrTransformer,
    IdentityTransformer,
    ListTransformer,
    OptionalTransformer,
    SubscriptedWrappedClassTransformer,
    TupleTransformer,
    UnionTransformer,
    WrappedClassTransformer,
)

_WRAPPER_LOCATION_ATTR = "__synchronicity_wrapper_location__"


def _make_wrapped_transformer(wrapped_class):
    """Helper to create a WrappedClassTransformer from a class with wrapper location set."""
    impl_ref = ImplQualifiedRef(module=wrapped_class.__module__, qualname=wrapped_class.__qualname__)
    wrapper_ref = WrapperRef("test_module", "TestClass")
    return WrappedClassTransformer(impl_ref, wrapper_ref)


def _materialize(annotation, **kwargs):
    """Annotation → TypeTransformerIR → runtime transformer (same path as codegen)."""
    ir = annotation_to_transformer_ir(annotation, **kwargs)
    return materialize_transformer_ir(ir, "synchronicity2")


@pytest.fixture
def wrapped_class():
    class TestClass:
        def __init__(self, value: int):
            self.value = value

    setattr(TestClass, _WRAPPER_LOCATION_ATTR, ("test_module", "TestClass"))
    return TestClass


class TestIdentityTransformer:
    """Test IdentityTransformer for primitive types."""

    def test_wrapped_type_int(self):
        transformer = IdentityTransformer(int)
        assert transformer.wrapped_type("test_module") == "int"

    def test_wrapped_type_str(self):
        transformer = IdentityTransformer(str)
        assert transformer.wrapped_type("test_module") == "str"

    def test_unwrap_expr_returns_same(self):
        transformer = IdentityTransformer(int)
        assert transformer.unwrap_expr("value") == "value"

    def test_wrap_expr_returns_same(self):
        transformer = IdentityTransformer(str)
        assert transformer.wrap_expr("test_module", "value") == "value"

    def test_needs_translation_false(self):
        transformer = IdentityTransformer(int)
        assert transformer.needs_translation() is False

    def test_execution_passthrough(self):
        """Test that identity transformer passes values through."""
        transformer = IdentityTransformer(int)

        # Unwrap should be identity
        value = 42
        unwrap_code = f"result = {transformer.unwrap_expr('value')}"
        exec(unwrap_code, {"value": value}, locals_dict := {})
        assert locals_dict["result"] == 42

        # Wrap should be identity
        wrap_code = f"result = {transformer.wrap_expr('test_module', 'value')}"
        exec(wrap_code, {"value": value}, locals_dict := {})
        assert locals_dict["result"] == 42


class TestWrappedClassTransformer:
    """Test WrappedClassTransformer for wrapped classes."""

    def test_wrapped_type_local_reference(self, wrapped_class):
        transformer = _make_wrapped_transformer(wrapped_class)
        # When target_module matches, should return just class name
        result = transformer.wrapped_type("test_module")
        assert result == "TestClass"

    def test_wrapped_type_cross_module_reference(self, wrapped_class):
        transformer = _make_wrapped_transformer(wrapped_class)
        # When target_module differs, should return fully qualified name
        result = transformer.wrapped_type("other_module")
        assert result == "test_module.TestClass"

    def test_unwrap_expr(self, wrapped_class):
        transformer = _make_wrapped_transformer(wrapped_class)
        assert transformer.unwrap_expr("obj") == "obj._impl_instance"

    def test_wrap_expr_local(self, wrapped_class):
        transformer = _make_wrapped_transformer(wrapped_class)
        result = transformer.wrap_expr("test_module", "impl")
        assert result == "TestClass._from_impl(impl)"

    def test_wrap_expr_cross_module(self, wrapped_class):
        transformer = _make_wrapped_transformer(wrapped_class)
        result = transformer.wrap_expr("other_module", "impl")
        assert result == "test_module.TestClass._from_impl(impl)"

    def test_needs_translation_true(self, wrapped_class):
        transformer = _make_wrapped_transformer(wrapped_class)
        assert transformer.needs_translation() is True


class TestListTransformer:
    """Test ListTransformer for list[T] types."""

    def test_wrapped_type_primitives(self):
        item_transformer = IdentityTransformer(int)
        transformer = ListTransformer(item_transformer)
        assert transformer.wrapped_type("test_module") == "list[int]"

    def test_wrapped_type_wrapped_class(self, wrapped_class):
        item_transformer = _make_wrapped_transformer(wrapped_class)
        transformer = ListTransformer(item_transformer)
        assert transformer.wrapped_type("test_module") == "list[TestClass]"

    def test_unwrap_expr_primitives(self):
        """Primitives don't need unwrapping."""
        item_transformer = IdentityTransformer(int)
        transformer = ListTransformer(item_transformer)
        assert transformer.unwrap_expr("values") == "values"

    def test_unwrap_expr_wrapped_class(self, wrapped_class):
        item_transformer = _make_wrapped_transformer(wrapped_class)
        transformer = ListTransformer(item_transformer)
        result = transformer.unwrap_expr("items")
        assert result == "[x._impl_instance for x in items]"

    def test_wrap_expr_wrapped_class(self, wrapped_class):
        item_transformer = _make_wrapped_transformer(wrapped_class)
        transformer = ListTransformer(item_transformer)
        result = transformer.wrap_expr("test_module", "impl_items")
        assert result == "[TestClass._from_impl(x) for x in impl_items]"

    def test_needs_translation(self, wrapped_class):
        # List of primitives doesn't need translation
        transformer1 = ListTransformer(IdentityTransformer(int))
        assert transformer1.needs_translation() is False

        # List of wrapped classes needs translation
        transformer2 = ListTransformer(_make_wrapped_transformer(wrapped_class))
        assert transformer2.needs_translation() is True

    def test_execution_list_comprehension(self):
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

    def test_wrapped_type(self, wrapped_class):
        key_transformer = IdentityTransformer(str)
        value_transformer = _make_wrapped_transformer(wrapped_class)
        transformer = DictTransformer(key_transformer, value_transformer)
        assert transformer.wrapped_type("test_module") == "dict[str, TestClass]"

    def test_unwrap_expr_primitives(self):
        """Dict with primitive values doesn't need unwrapping."""
        key_transformer = IdentityTransformer(str)
        value_transformer = IdentityTransformer(int)
        transformer = DictTransformer(key_transformer, value_transformer)
        assert transformer.unwrap_expr("mapping") == "mapping"

    def test_unwrap_expr_wrapped_values(self, wrapped_class):
        key_transformer = IdentityTransformer(str)
        value_transformer = _make_wrapped_transformer(wrapped_class)
        transformer = DictTransformer(key_transformer, value_transformer)
        result = transformer.unwrap_expr("mapping")
        assert result == "{k: v._impl_instance for k, v in mapping.items()}"

    def test_wrap_expr_wrapped_values(self, wrapped_class):
        key_transformer = IdentityTransformer(str)
        value_transformer = _make_wrapped_transformer(wrapped_class)
        transformer = DictTransformer(key_transformer, value_transformer)
        result = transformer.wrap_expr("test_module", "impl_mapping")
        assert result == "{k: TestClass._from_impl(v) for k, v in impl_mapping.items()}"

    def test_needs_translation(self, wrapped_class):
        # Dict with primitive values doesn't need translation
        transformer1 = DictTransformer(IdentityTransformer(str), IdentityTransformer(int))
        assert transformer1.needs_translation() is False

        # Dict with wrapped values needs translation
        transformer2 = DictTransformer(IdentityTransformer(str), _make_wrapped_transformer(wrapped_class))
        assert transformer2.needs_translation() is True

    def test_execution_dict_comprehension(self):
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

    def test_wrapped_type_variable_length(self):
        """Test tuple[T, ...] formatting."""
        item_transformer = IdentityTransformer(int)
        transformer = TupleTransformer([item_transformer])
        assert transformer.wrapped_type("test_module") == "tuple[int, ...]"

    def test_wrapped_type_fixed_size(self, wrapped_class):
        """Test tuple[T1, T2] formatting."""
        transformers = [IdentityTransformer(int), _make_wrapped_transformer(wrapped_class)]
        transformer = TupleTransformer(transformers)
        assert transformer.wrapped_type("test_module") == "tuple[int, TestClass]"

    def test_unwrap_expr_variable_length(self, wrapped_class):
        item_transformer = _make_wrapped_transformer(wrapped_class)
        transformer = TupleTransformer([item_transformer])
        result = transformer.unwrap_expr("items")
        assert result == "tuple(x._impl_instance for x in items)"

    def test_unwrap_expr_fixed_size(self, wrapped_class):
        """Test fixed-size tuple unwrapping by index."""
        transformers = [IdentityTransformer(int), _make_wrapped_transformer(wrapped_class)]
        transformer = TupleTransformer(transformers)
        result = transformer.unwrap_expr("items")
        assert result == "(items[0], items[1]._impl_instance)"

    def test_wrap_expr_fixed_size(self, wrapped_class):
        transformers = [IdentityTransformer(int), _make_wrapped_transformer(wrapped_class)]
        transformer = TupleTransformer(transformers)
        result = transformer.wrap_expr("test_module", "impl_items")
        assert result == "(impl_items[0], TestClass._from_impl(impl_items[1]))"

    def test_execution_fixed_size_tuple(self):
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

    def test_wrapped_type(self, wrapped_class):
        inner_transformer = _make_wrapped_transformer(wrapped_class)
        transformer = OptionalTransformer(inner_transformer)
        assert transformer.wrapped_type("test_module") == "typing.Union[TestClass, None]"

    def test_unwrap_expr(self, wrapped_class):
        inner_transformer = _make_wrapped_transformer(wrapped_class)
        transformer = OptionalTransformer(inner_transformer)
        result = transformer.unwrap_expr("obj")
        assert result == "obj._impl_instance if obj is not None else None"

    def test_wrap_expr(self, wrapped_class):
        inner_transformer = _make_wrapped_transformer(wrapped_class)
        transformer = OptionalTransformer(inner_transformer)
        result = transformer.wrap_expr("test_module", "impl")
        assert result == "TestClass._from_impl(impl) if impl is not None else None"

    def test_needs_translation(self, wrapped_class):
        # Optional primitive doesn't need translation
        transformer1 = OptionalTransformer(IdentityTransformer(int))
        assert transformer1.needs_translation() is False

        # Optional wrapped class needs translation
        transformer2 = OptionalTransformer(_make_wrapped_transformer(wrapped_class))
        assert transformer2.needs_translation() is True

    def test_execution_unwrap_none(self):
        """Test unwrap with None value."""
        unwrap_expr = "value._impl_instance if value is not None else None"
        result = eval(unwrap_expr, {"value": None})
        assert result is None

    def test_execution_unwrap_not_none(self):
        """Test unwrap with non-None value."""

        class MockWrapper:
            def __init__(self, value):
                self._impl_instance = value

        obj = MockWrapper(42)
        unwrap_expr = "value._impl_instance if value is not None else None"
        result = eval(unwrap_expr, {"value": obj})
        assert result == 42


class TestUnionTransformer:
    """Test UnionTransformer for general Union[T1, T2] types."""

    def test_wrapped_type(self, wrapped_class):
        transformer = UnionTransformer([IdentityTransformer(int), _make_wrapped_transformer(wrapped_class)])
        assert transformer.wrapped_type("test_module") == "typing.Union[int, TestClass]"

    def test_needs_translation(self, wrapped_class):
        transformer = UnionTransformer([IdentityTransformer(int), _make_wrapped_transformer(wrapped_class)])
        assert transformer.needs_translation() is True

        identity_only = UnionTransformer([IdentityTransformer(int), IdentityTransformer(str)])
        assert identity_only.needs_translation() is False

    def test_wrap_expr_mixed_union(self, wrapped_class):
        transformer = UnionTransformer([IdentityTransformer(int), _make_wrapped_transformer(wrapped_class)])
        result = transformer.wrap_expr("test_module", "value")
        assert "TestClass._from_impl(_v)" in result
        assert "isinstance(_v, test.unit.transformers.test_type_transformers.TestUnionTransformer" not in result
        assert "Unexpected value for union translation" in result

    def test_unwrap_expr_mixed_union(self, wrapped_class):
        transformer = UnionTransformer([IdentityTransformer(int), _make_wrapped_transformer(wrapped_class)])
        result = transformer.unwrap_expr("value")
        assert 'hasattr(_v, "_impl_instance")' in result
        assert 'getattr(_v, "_impl_instance")' in result

    def test_execution_wrap_expr_returns_wrapper(self, wrapped_class):
        transformer = UnionTransformer([IdentityTransformer(int), _make_wrapped_transformer(wrapped_class)])

        class TestClass:
            @staticmethod
            def _from_impl(impl):
                return ("wrapped", impl.value)

        impl = wrapped_class(9)
        expr = transformer.wrap_expr("test_module", "value")
        module = sys.modules[wrapped_class.__module__]
        setattr(module, wrapped_class.__name__, wrapped_class)
        result = eval(expr, {"value": impl, "TestClass": TestClass, "test": __import__("test")})
        assert result == ("wrapped", 9)

    def test_execution_unwrap_expr_returns_impl(self, wrapped_class):
        transformer = UnionTransformer([IdentityTransformer(int), _make_wrapped_transformer(wrapped_class)])

        class Wrapper:
            def __init__(self, impl):
                self._impl_instance = impl

        impl = wrapped_class(9)
        wrapper = Wrapper(impl)
        expr = transformer.unwrap_expr("value")
        module = sys.modules[wrapped_class.__module__]
        setattr(module, wrapped_class.__name__, wrapped_class)
        result = eval(expr, {"value": wrapper, "test": __import__("test")})
        assert result is impl

    def test_rejects_ambiguous_translated_union(self, wrapped_class):
        transformer = UnionTransformer(
            [
                ListTransformer(_make_wrapped_transformer(wrapped_class)),
                ListTransformer(IdentityTransformer(int)),
            ],
            source_label="pkg.mod.func return",
        )
        with pytest.raises(TypeError, match=r"pkg\.mod\.func return: .*list\[test_module\.TestClass\].*list\[int\]"):
            transformer.wrap_expr("test_module", "value")

    def test_allows_same_wrapped_generic_base(self, wrapped_class):
        impl_ref = ImplQualifiedRef(module=wrapped_class.__module__, qualname=wrapped_class.__qualname__)
        wrapper_ref = WrapperRef("test_module", "TestClass")
        generic_str = SubscriptedWrappedClassTransformer(impl_ref, wrapper_ref, [IdentityTransformer(str)])
        generic_list_int = SubscriptedWrappedClassTransformer(
            impl_ref,
            wrapper_ref,
            [ListTransformer(IdentityTransformer(int))],
        )

        transformer = UnionTransformer([generic_str, generic_list_int], source_label="pkg.mod.func return")

        wrap_expr = transformer.wrap_expr("test_module", "value")
        unwrap_expr = transformer.unwrap_expr("value")

        assert "TestClass._from_impl(_v)" in wrap_expr
        assert wrap_expr.count("TestClass._from_impl(_v)") == 1
        assert unwrap_expr.count('hasattr(_v, "_impl_instance")') == 1
        assert 'getattr(_v, "_impl_instance")' in unwrap_expr


class TestGeneratorTransformer:
    """Test GeneratorTransformer for Generator/AsyncGenerator types."""

    def test_wrapped_type_async_generator(self, wrapped_class):
        from synchronicity2.codegen.type_transformer import AsyncGeneratorTransformer

        yield_transformer = _make_wrapped_transformer(wrapped_class)
        transformer = AsyncGeneratorTransformer(yield_transformer, send_type_str="None")
        assert transformer.wrapped_type("test_module", is_async=True) == "typing.AsyncGenerator[TestClass, None]"
        # Sync context should preserve send type (even if it's just None)
        assert transformer.wrapped_type("test_module", is_async=False) == "typing.Generator[TestClass, None, None]"

    def test_wrapped_type_async_iterator_no_send(self):
        """AsyncIterator doesn't have send type."""
        from synchronicity2.codegen.type_transformer import AsyncGeneratorTransformer

        yield_transformer = IdentityTransformer(int)
        transformer = AsyncGeneratorTransformer(yield_transformer, send_type_str=None)
        assert transformer.wrapped_type("test_module", is_async=True) == "typing.AsyncGenerator[int]"
        assert transformer.wrapped_type("test_module", is_async=False) == "typing.Generator[int, None, None]"

    def test_wrapped_type_sync_generator(self):
        from synchronicity2.codegen.type_transformer import SyncGeneratorTransformer

        yield_transformer = IdentityTransformer(str)
        transformer = SyncGeneratorTransformer(yield_transformer)
        assert transformer.wrapped_type("test_module") == "typing.Generator[str, None, None]"

    def test_two_way_generator_with_send_type(self):
        """Test that two-way generators preserve send type in both contexts."""
        from synchronicity2.codegen.type_transformer import AsyncGeneratorTransformer

        yield_transformer = IdentityTransformer(str)
        # Two-way generator: yields str, accepts str via send
        transformer = AsyncGeneratorTransformer(yield_transformer, send_type_str="str")

        # Async context: AsyncGenerator[str, str]
        assert transformer.wrapped_type("test_module", is_async=True) == "typing.AsyncGenerator[str, str]"

        # Sync context: Generator[str, str, None]
        # Should preserve send type to support two-way generators
        assert transformer.wrapped_type("test_module", is_async=False) == "typing.Generator[str, str, None]"

    def test_two_way_generator_with_int_send_type(self):
        """Test two-way generator with int send type."""
        from synchronicity2.codegen.type_transformer import AsyncGeneratorTransformer

        yield_transformer = IdentityTransformer(int)
        transformer = AsyncGeneratorTransformer(yield_transformer, send_type_str="int")

        # Both contexts should preserve send type
        assert transformer.wrapped_type("test_module", is_async=True) == "typing.AsyncGenerator[int, int]"
        assert transformer.wrapped_type("test_module", is_async=False) == "typing.Generator[int, int, None]"

    def test_one_way_generator_send_none(self):
        """Test one-way generator (send type is None, no send support needed)."""
        from synchronicity2.codegen.type_transformer import AsyncGeneratorTransformer

        yield_transformer = IdentityTransformer(str)
        # One-way generator: yields str, doesn't use send
        transformer = AsyncGeneratorTransformer(yield_transformer, send_type_str="None")

        # Both should have None as send type
        assert transformer.wrapped_type("test_module", is_async=True) == "typing.AsyncGenerator[str, None]"
        assert transformer.wrapped_type("test_module", is_async=False) == "typing.Generator[str, None, None]"

    def test_needs_translation(self, wrapped_class):
        from synchronicity2.codegen.type_transformer import AsyncGeneratorTransformer, SyncGeneratorTransformer

        # Async generators ALWAYS need translation (for synchronizer integration)
        transformer1 = AsyncGeneratorTransformer(IdentityTransformer(int))
        assert transformer1.needs_translation() is True

        # Generator of wrapped classes also needs translation
        transformer2 = AsyncGeneratorTransformer(_make_wrapped_transformer(wrapped_class))
        assert transformer2.needs_translation() is True

        # Sync generators only need translation if yield type needs translation
        transformer3 = SyncGeneratorTransformer(IdentityTransformer(int))
        assert transformer3.needs_translation() is False

        transformer4 = SyncGeneratorTransformer(_make_wrapped_transformer(wrapped_class))
        assert transformer4.needs_translation() is True


class TestMaterializeFromAnnotation:
    """``annotation_to_transformer_ir`` + ``materialize_transformer_ir`` (codegen path)."""

    def test_create_primitive(self):
        transformer = _materialize(int)
        assert isinstance(transformer, IdentityStrTransformer)

    def test_create_wrapped_class(self, wrapped_class):
        transformer = _materialize(wrapped_class)
        assert isinstance(transformer, WrappedClassTransformer)

    def test_create_list(self):
        from typing import List

        transformer = _materialize(List[int])
        assert isinstance(transformer, ListTransformer)
        assert isinstance(transformer.item_transformer, IdentityStrTransformer)

    def test_create_dict(self):
        from typing import Dict

        transformer = _materialize(Dict[str, int])
        assert isinstance(transformer, DictTransformer)

    def test_create_tuple_fixed(self, wrapped_class):
        from typing import Tuple

        transformer = _materialize(Tuple[int, wrapped_class])
        assert isinstance(transformer, TupleTransformer)
        assert len(transformer.item_transformers) == 2

    def test_create_optional(self, wrapped_class):
        from typing import Optional

        transformer = _materialize(Optional[wrapped_class])
        assert isinstance(transformer, OptionalTransformer)
        assert isinstance(transformer.inner_transformer, WrappedClassTransformer)

    def test_create_union(self, wrapped_class):
        transformer = _materialize(int | wrapped_class)
        assert isinstance(transformer, UnionTransformer)
        assert len(transformer.item_transformers) == 2

    def test_create_async_generator(self):
        from typing import AsyncGenerator

        transformer = _materialize(AsyncGenerator[str, None])
        assert isinstance(transformer, AsyncGeneratorTransformer)

    def test_nested_list_of_optional_wrapped(self, wrapped_class):
        """Test nested type: list[Optional[WrappedClass]]."""
        from typing import List, Optional

        transformer = _materialize(List[Optional[wrapped_class]])
        assert isinstance(transformer, ListTransformer)
        assert isinstance(transformer.item_transformer, OptionalTransformer)
        assert isinstance(transformer.item_transformer.inner_transformer, WrappedClassTransformer)

        # Check type signature
        result = transformer.wrapped_type("test_module")
        assert result == "list[typing.Union[TestClass, None]]"

        # Check needs translation
        assert transformer.needs_translation() is True

    def test_create_coroutine_with_args(self):
        """Test Coroutine[Any, Any, str] creates CoroutineTransformer."""
        from typing import Any, Coroutine

        transformer = _materialize(Coroutine[Any, Any, str])
        assert isinstance(transformer, CoroutineTransformer)

        # Check that return type is unwrapped to str
        result = transformer.wrapped_type("test_module")
        assert result == "str"

    def test_create_coroutine_bare(self):
        """Test bare Coroutine (no type args) creates CoroutineTransformer with identity return."""
        from typing import Coroutine

        transformer = _materialize(Coroutine)
        assert isinstance(transformer, CoroutineTransformer)
        assert isinstance(transformer.return_transformer, IdentityStrTransformer)

    def test_create_awaitable_with_args(self):
        """Test Awaitable[str] creates AwaitableTransformer."""
        from typing import Awaitable

        transformer = _materialize(Awaitable[str])
        assert isinstance(transformer, AwaitableTransformer)

        # Check that return type is unwrapped to str
        result = transformer.wrapped_type("test_module")
        assert result == "str"

    def test_create_awaitable_bare(self):
        """Test bare Awaitable (no type args) creates AwaitableTransformer with identity return."""
        from typing import Awaitable

        transformer = _materialize(Awaitable)
        assert isinstance(transformer, AwaitableTransformer)
        assert isinstance(transformer.return_transformer, IdentityStrTransformer)


class TestComplexNestedTypes:
    """Test complex nested type transformations."""

    def test_dict_of_list_of_wrapped(self, wrapped_class):
        """Test dict[str, list[WrappedClass]]."""
        from typing import Dict, List

        transformer = _materialize(Dict[str, List[wrapped_class]])

        # Check type signature
        result = transformer.wrapped_type("test_module")
        assert result == "dict[str, list[TestClass]]"

        # Check unwrap expression
        unwrap = transformer.unwrap_expr("data")
        assert "[x._impl_instance for x in v]" in unwrap
        assert "for k, v in data.items()" in unwrap

        # Check needs translation
        assert transformer.needs_translation() is True

    def test_tuple_of_mixed_types(self, wrapped_class):
        """Test tuple[int, WrappedClass, str]."""
        from typing import Tuple

        transformer = _materialize(Tuple[int, wrapped_class, str])

        # Check type signature
        result = transformer.wrapped_type("test_module")
        assert result == "tuple[int, TestClass, str]"

        # Check unwrap - should unwrap only the wrapped class at index 1
        unwrap = transformer.unwrap_expr("items")
        assert "items[0]" in unwrap
        assert "items[1]._impl_instance" in unwrap
        assert "items[2]" in unwrap

    def test_execution_nested_unwrap(self):
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
