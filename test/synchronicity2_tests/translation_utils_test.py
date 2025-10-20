"""Tests for type translation utilities in synchronicity2.codegen.

These tests verify the object-based type translation system that uses
inspect.get_annotations(eval_str=True) and object identity checks.
"""

import inspect
import pytest
import typing

from synchronicity2.codegen import (
    build_unwrap_expr,
    build_wrap_expr,
    format_type_for_annotation,
    needs_translation,
)
from synchronicity2.synchronizer import Synchronizer


# Mock implementation classes
class _impl_Foo:
    """Mock implementation class."""

    pass


class _impl_Bar:
    """Mock implementation class."""

    pass


@pytest.fixture
def test_synchronizer():
    """Create a test synchronizer with wrapped classes."""
    sync = Synchronizer("test_lib")
    # Register the mock classes as wrapped
    sync._wrapped[_impl_Foo] = ("test_module", "Foo")
    sync._wrapped[_impl_Bar] = ("test_module", "Bar")
    return sync


class TestNeedsTranslation:
    """Tests for needs_translation() using object identity checks."""

    def test_wrapped_type_needs_translation(self, test_synchronizer):
        """Test that wrapped types are detected."""
        assert needs_translation(_impl_Foo, test_synchronizer) is True

    def test_list_of_wrapped_needs_translation(self, test_synchronizer):
        """Test that list[WrappedClass] needs translation."""
        annotation = typing.List[_impl_Bar]
        assert needs_translation(annotation, test_synchronizer) is True

    def test_primitive_no_translation(self, test_synchronizer):
        """Test that primitives don't need translation."""
        assert needs_translation(str, test_synchronizer) is False
        assert needs_translation(int, test_synchronizer) is False

    def test_any_no_translation(self, test_synchronizer):
        """Test that typing.Any doesn't need translation."""
        assert needs_translation(typing.Any, test_synchronizer) is False

    def test_empty_annotation_no_translation(self, test_synchronizer):
        """Test that Signature.empty doesn't need translation."""
        assert needs_translation(inspect.Signature.empty, test_synchronizer) is False

    def test_dict_with_wrapped_values_needs_translation(self, test_synchronizer):
        """Test that dict[str, WrappedClass] needs translation."""
        annotation = typing.Dict[str, _impl_Foo]
        assert needs_translation(annotation, test_synchronizer) is True

    def test_optional_wrapped_needs_translation(self, test_synchronizer):
        """Test that Optional[WrappedClass] needs translation."""
        annotation = typing.Optional[_impl_Foo]
        assert needs_translation(annotation, test_synchronizer) is True

    def test_nested_wrapped_needs_translation(self, test_synchronizer):
        """Test that nested structures with wrapped types need translation."""
        annotation = typing.List[typing.Dict[str, _impl_Bar]]
        assert needs_translation(annotation, test_synchronizer) is True


class TestFormatTypeForAnnotation:
    """Tests for format_type_for_annotation() with object-based type resolution."""

    def test_wrapped_type_local_module(self, test_synchronizer):
        """Test formatting a wrapped type in the same target module."""
        result = format_type_for_annotation(_impl_Foo, test_synchronizer, "test_module")
        assert result == "Foo"

    def test_wrapped_type_cross_module(self, test_synchronizer):
        """Test formatting a wrapped type from a different module."""
        result = format_type_for_annotation(_impl_Foo, test_synchronizer, "other_module")
        assert result == "test_module.Foo"

    def test_list_of_wrapped(self, test_synchronizer):
        """Test formatting list[WrappedClass]."""
        annotation = typing.List[_impl_Foo]
        result = format_type_for_annotation(annotation, test_synchronizer, "test_module")
        assert "list[Foo]" in result

    def test_dict_with_wrapped_values(self, test_synchronizer):
        """Test formatting dict[str, WrappedClass]."""
        annotation = typing.Dict[str, _impl_Bar]
        result = format_type_for_annotation(annotation, test_synchronizer, "test_module")
        assert "dict[str, Bar]" in result

    def test_optional_wrapped(self, test_synchronizer):
        """Test formatting Optional[WrappedClass]."""
        annotation = typing.Optional[_impl_Foo]
        result = format_type_for_annotation(annotation, test_synchronizer, "test_module")
        assert "Union" in result or "Optional" in result
        assert "Foo" in result

    def test_primitive_type(self, test_synchronizer):
        """Test that primitive types are formatted correctly."""
        result = format_type_for_annotation(str, test_synchronizer, "test_module")
        assert result == "str"

    def test_none_type(self, test_synchronizer):
        """Test that None type is formatted correctly."""
        result = format_type_for_annotation(type(None), test_synchronizer, "test_module")
        assert result == "None"


class TestBuildUnwrapExpr:
    """Tests for build_unwrap_expr() with object-based type checks."""

    def test_direct_wrapped_type(self, test_synchronizer):
        """Test unwrapping a direct wrapped type."""
        expr = build_unwrap_expr(_impl_Foo, test_synchronizer, "my_var")
        assert expr == "my_var._impl_instance"

    def test_list_of_wrapped(self, test_synchronizer):
        """Test unwrapping list[WrappedClass]."""
        annotation = typing.List[_impl_Foo]
        expr = build_unwrap_expr(annotation, test_synchronizer, "items")
        assert "for x in items" in expr
        assert "._impl_instance" in expr
        assert expr.startswith("[")
        assert expr.endswith("]")

    def test_dict_with_wrapped_values(self, test_synchronizer):
        """Test unwrapping dict[str, WrappedClass]."""
        annotation = typing.Dict[str, _impl_Bar]
        expr = build_unwrap_expr(annotation, test_synchronizer, "mapping")
        assert ".items()" in expr
        assert "._impl_instance" in expr
        assert "{" in expr

    def test_optional_wrapped_type(self, test_synchronizer):
        """Test unwrapping Optional[WrappedClass]."""
        annotation = typing.Optional[_impl_Foo]
        expr = build_unwrap_expr(annotation, test_synchronizer, "maybe_val")
        assert "if maybe_val is not None else None" in expr
        assert "._impl_instance" in expr

    def test_tuple_of_wrapped(self, test_synchronizer):
        """Test unwrapping tuple[WrappedClass, ...]."""
        annotation = typing.Tuple[_impl_Foo, ...]
        expr = build_unwrap_expr(annotation, test_synchronizer, "tup")
        assert "tuple(" in expr
        assert "for x in tup" in expr
        assert "._impl_instance" in expr

    def test_nested_list_dict(self, test_synchronizer):
        """Test unwrapping nested list[dict[str, WrappedClass]]."""
        annotation = typing.List[typing.Dict[str, _impl_Foo]]
        expr = build_unwrap_expr(annotation, test_synchronizer, "data")
        # Should have nested comprehensions
        assert "for x in data" in expr
        assert ".items()" in expr
        assert "._impl_instance" in expr

    def test_primitive_no_unwrap(self, test_synchronizer):
        """Test that primitives are returned as-is."""
        expr = build_unwrap_expr(str, test_synchronizer, "text")
        assert expr == "text"

    def test_any_no_unwrap(self, test_synchronizer):
        """Test that typing.Any is not unwrapped."""
        expr = build_unwrap_expr(typing.Any, test_synchronizer, "anything")
        assert expr == "anything"

    def test_empty_annotation_no_unwrap(self, test_synchronizer):
        """Test that Signature.empty is not unwrapped."""
        expr = build_unwrap_expr(inspect.Signature.empty, test_synchronizer, "val")
        assert expr == "val"


class TestBuildWrapExpr:
    """Tests for build_wrap_expr() with object-based type checks and module awareness."""

    def test_direct_wrapped_type_local(self, test_synchronizer):
        """Test wrapping a direct wrapped type in the same module."""
        expr = build_wrap_expr(_impl_Foo, test_synchronizer, "test_module", "result")
        assert expr == "Foo._from_impl(result)"

    def test_direct_wrapped_type_cross_module(self, test_synchronizer):
        """Test wrapping a direct wrapped type from a different module."""
        expr = build_wrap_expr(_impl_Foo, test_synchronizer, "other_module", "result")
        assert expr == "test_module.Foo._from_impl(result)"

    def test_list_of_wrapped(self, test_synchronizer):
        """Test wrapping list[WrappedClass]."""
        annotation = typing.List[_impl_Bar]
        expr = build_wrap_expr(annotation, test_synchronizer, "test_module", "items")
        assert "Bar._from_impl(x)" in expr
        assert "for x in items" in expr
        assert expr.startswith("[")

    def test_dict_with_wrapped_values(self, test_synchronizer):
        """Test wrapping dict[str, WrappedClass]."""
        annotation = typing.Dict[str, _impl_Foo]
        expr = build_wrap_expr(annotation, test_synchronizer, "test_module", "mapping")
        assert "Foo._from_impl(v)" in expr
        assert ".items()" in expr
        assert "{" in expr

    def test_optional_wrapped_type(self, test_synchronizer):
        """Test wrapping Optional[WrappedClass]."""
        annotation = typing.Optional[_impl_Bar]
        expr = build_wrap_expr(annotation, test_synchronizer, "test_module", "maybe_val")
        assert "Bar._from_impl(maybe_val)" in expr
        assert "if maybe_val is not None else None" in expr

    def test_tuple_of_wrapped(self, test_synchronizer):
        """Test wrapping tuple[WrappedClass, ...]."""
        annotation = typing.Tuple[_impl_Foo, ...]
        expr = build_wrap_expr(annotation, test_synchronizer, "test_module", "tup")
        assert "Foo._from_impl(x)" in expr
        assert "tuple(" in expr
        assert "for x in tup" in expr

    def test_nested_list_dict(self, test_synchronizer):
        """Test wrapping nested list[dict[str, WrappedClass]]."""
        annotation = typing.List[typing.Dict[str, _impl_Bar]]
        expr = build_wrap_expr(annotation, test_synchronizer, "test_module", "data")
        # Should have nested comprehensions
        assert "Bar._from_impl(v)" in expr
        assert "for x in data" in expr
        assert ".items()" in expr

    def test_primitive_no_wrap(self, test_synchronizer):
        """Test that primitives are returned as-is."""
        expr = build_wrap_expr(int, test_synchronizer, "test_module", "number")
        assert expr == "number"

    def test_any_no_wrap(self, test_synchronizer):
        """Test that typing.Any is not wrapped."""
        expr = build_wrap_expr(typing.Any, test_synchronizer, "test_module", "anything")
        assert expr == "anything"

    def test_cross_module_qualification(self, test_synchronizer):
        """Test that cross-module types are fully qualified."""
        # When wrapping in a different module, should use full path
        expr = build_wrap_expr(_impl_Foo, test_synchronizer, "different_module", "result")
        assert "test_module.Foo._from_impl(result)" == expr


class TestEdgeCases:
    """Tests for edge cases and complex scenarios."""

    def test_multiple_wrapped_classes_in_dict(self, test_synchronizer):
        """Test dict with wrapped key and value types."""
        annotation = typing.Dict[_impl_Foo, _impl_Bar]
        # Keys are not typically translated, only values
        expr = build_wrap_expr(annotation, test_synchronizer, "test_module", "data")
        # Should still work but only translate values
        assert "._from_impl(" in expr or expr == "data"

    def test_deeply_nested_structure(self, test_synchronizer):
        """Test deeply nested type structure."""
        annotation = typing.List[typing.Optional[typing.Dict[str, _impl_Foo]]]
        expr = build_unwrap_expr(annotation, test_synchronizer, "deep")
        # Should handle deep nesting
        assert "._impl_instance" in expr

    def test_empty_synchronizer(self):
        """Test with no wrapped classes."""
        empty_sync = Synchronizer("empty")
        assert needs_translation(_impl_Foo, empty_sync) is False
        expr = build_unwrap_expr(_impl_Foo, empty_sync, "val")
        assert expr == "val"  # No translation without registration

    def test_union_with_multiple_wrapped_types(self, test_synchronizer):
        """Test Union with multiple wrapped types."""
        annotation = typing.Union[_impl_Foo, _impl_Bar]
        # Should detect that translation is needed
        assert needs_translation(annotation, test_synchronizer) is True

    def test_generic_alias_with_wrapped_type(self, test_synchronizer):
        """Test list generic alias with wrapped type."""
        annotation = list[_impl_Foo]  # Python 3.9+ syntax
        assert needs_translation(annotation, test_synchronizer) is True
        expr = build_unwrap_expr(annotation, test_synchronizer, "items")
        assert "._impl_instance" in expr


class TestForwardReferenceErrors:
    """Tests that ForwardRef objects raise helpful errors."""

    def test_forward_ref_raises_error(self, test_synchronizer):
        """Test that ForwardRef raises a TypeError with helpful message."""
        # Create a ForwardRef (simulating what happens with quoted generic args)
        forward_ref = typing.ForwardRef("Foo")

        # Should raise TypeError with helpful message
        with pytest.raises(TypeError) as exc_info:
            needs_translation(forward_ref, test_synchronizer)

        error_msg = str(exc_info.value)
        assert "unresolved forward reference" in error_msg
        assert "Foo" in error_msg
        assert "quote the entire type annotation" in error_msg

    def test_forward_ref_in_format_raises_error(self, test_synchronizer):
        """Test that ForwardRef in format_type_for_annotation raises error."""

        class MockForwardRef:
            __forward_arg__ = "MyClass"

        forward_ref = MockForwardRef()

        with pytest.raises(TypeError) as exc_info:
            format_type_for_annotation(forward_ref, test_synchronizer, "test_module")

        error_msg = str(exc_info.value)
        assert "MyClass" in error_msg
        assert "unresolved forward reference" in error_msg
