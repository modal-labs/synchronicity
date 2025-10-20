"""Tests for type translation utilities in synchronicity2.codegen."""

import pytest
import typing

from synchronicity2.codegen import (
    build_unwrap_expr,
    build_wrap_expr,
    get_wrapped_classes,
    needs_translation,
    translate_type_annotation,
)


# Mock wrapped items for testing
class _impl_Foo:
    """Mock implementation class."""

    pass


class _impl_Bar:
    """Mock implementation class."""

    pass


# Simulate what Library.wrap() produces
MOCK_WRAPPED_ITEMS = {
    _impl_Foo: ("test_module", "Foo"),
    _impl_Bar: ("test_module", "Bar"),
}


@pytest.fixture
def wrapped_classes():
    """Fixture providing wrapped classes mapping."""
    return get_wrapped_classes(MOCK_WRAPPED_ITEMS)


class TestGetWrappedClasses:
    """Tests for get_wrapped_classes()."""

    def test_extracts_class_names(self):
        """Test that it extracts wrapper name -> impl qualified name mapping."""
        result = get_wrapped_classes(MOCK_WRAPPED_ITEMS)
        assert isinstance(result, dict)
        assert "Foo" in result
        assert "Bar" in result

    def test_builds_qualified_names(self):
        """Test that implementation names are fully qualified."""
        result = get_wrapped_classes(MOCK_WRAPPED_ITEMS)
        # Should be module.ClassName format
        assert "." in result["Foo"]
        assert "_impl_Foo" in result["Foo"]

    def test_ignores_non_classes(self):
        """Test that non-class objects are ignored."""

        def some_function():
            pass

        items_with_function = {
            _impl_Foo: ("test_module", "Foo"),
            some_function: ("test_module", "some_function"),
        }
        result = get_wrapped_classes(items_with_function)
        assert "Foo" in result
        assert "some_function" not in result


class TestTranslateTypeAnnotation:
    """Tests for translate_type_annotation()."""

    def test_direct_wrapped_type(self, wrapped_classes):
        """Test translating a direct wrapped class type."""
        wrapper_str, impl_str = translate_type_annotation(_impl_Foo, wrapped_classes, "test_translation_utils_test")
        assert "Foo" == wrapper_str
        assert "_impl_Foo" in impl_str

    def test_list_of_wrapped_type(self, wrapped_classes):
        """Test translating list[WrappedClass]."""
        annotation = typing.List[_impl_Foo]
        wrapper_str, impl_str = translate_type_annotation(annotation, wrapped_classes, "test_translation_utils_test")
        assert "Foo" in wrapper_str
        assert "_impl_Foo" in impl_str
        assert "list" in wrapper_str.lower()

    def test_dict_with_wrapped_values(self, wrapped_classes):
        """Test translating dict[str, WrappedClass]."""
        annotation = typing.Dict[str, _impl_Bar]
        wrapper_str, impl_str = translate_type_annotation(annotation, wrapped_classes, "test_translation_utils_test")
        assert "Bar" in wrapper_str
        assert "_impl_Bar" in impl_str
        assert "dict" in wrapper_str.lower()

    def test_optional_wrapped_type(self, wrapped_classes):
        """Test translating Optional[WrappedClass]."""
        annotation = typing.Optional[_impl_Foo]
        wrapper_str, impl_str = translate_type_annotation(annotation, wrapped_classes, "test_translation_utils_test")
        assert "Foo" in wrapper_str
        assert "_impl_Foo" in impl_str

    def test_primitive_type_unchanged(self, wrapped_classes):
        """Test that primitive types are not translated."""
        wrapper_str, impl_str = translate_type_annotation(str, wrapped_classes, "test_translation_utils_test")
        assert wrapper_str == impl_str
        assert "str" in wrapper_str

    def test_any_type_unchanged(self, wrapped_classes):
        """Test that typing.Any is not translated."""
        wrapper_str, impl_str = translate_type_annotation(typing.Any, wrapped_classes, "test_translation_utils_test")
        assert wrapper_str == impl_str
        assert "Any" in wrapper_str


class TestNeedsTranslation:
    """Tests for needs_translation()."""

    def test_wrapped_typeneeds_translation(self, wrapped_classes):
        """Test that wrapped types are detected."""
        assert needs_translation(_impl_Foo, wrapped_classes) is True

    def test_list_of_wrappedneeds_translation(self, wrapped_classes):
        """Test that list[WrappedClass] needs translation."""
        annotation = typing.List[_impl_Bar]
        assert needs_translation(annotation, wrapped_classes) is True

    def test_primitive_no_translation(self, wrapped_classes):
        """Test that primitives don't need translation."""
        assert needs_translation(str, wrapped_classes) is False
        assert needs_translation(int, wrapped_classes) is False

    def test_any_no_translation(self, wrapped_classes):
        """Test that typing.Any doesn't need translation."""
        assert needs_translation(typing.Any, wrapped_classes) is False

    def test_empty_annotation_no_translation(self, wrapped_classes):
        """Test that Signature.empty doesn't need translation."""
        import inspect

        assert needs_translation(inspect.Signature.empty, wrapped_classes) is False


class TestBuildUnwrapExpr:
    """Tests for build_unwrap_expr()."""

    def test_direct_wrapped_type(self, wrapped_classes):
        """Test unwrapping a direct wrapped type."""
        expr = build_unwrap_expr(_impl_Foo, wrapped_classes, "my_var")
        assert expr == "my_var._impl_instance"

    def test_list_of_wrapped(self, wrapped_classes):
        """Test unwrapping list[WrappedClass]."""
        annotation = typing.List[_impl_Foo]
        expr = build_unwrap_expr(annotation, wrapped_classes, "items")
        assert "for x in items" in expr
        assert "._impl_instance" in expr
        assert expr.startswith("[")
        assert expr.endswith("]")

    def test_dict_with_wrapped_values(self, wrapped_classes):
        """Test unwrapping dict[str, WrappedClass]."""
        annotation = typing.Dict[str, _impl_Bar]
        expr = build_unwrap_expr(annotation, wrapped_classes, "mapping")
        assert ".items()" in expr
        assert "._impl_instance" in expr
        assert "{" in expr

    def test_optional_wrapped_type(self, wrapped_classes):
        """Test unwrapping Optional[WrappedClass]."""
        annotation = typing.Optional[_impl_Foo]
        expr = build_unwrap_expr(annotation, wrapped_classes, "maybe_val")
        assert "if maybe_val is not None else None" in expr
        assert "._impl_instance" in expr

    def test_tuple_of_wrapped(self, wrapped_classes):
        """Test unwrapping tuple[WrappedClass, ...]."""
        annotation = typing.Tuple[_impl_Foo, ...]
        expr = build_unwrap_expr(annotation, wrapped_classes, "tup")
        assert "tuple(" in expr
        assert "for x in tup" in expr
        assert "._impl_instance" in expr

    def test_nested_list_dict(self, wrapped_classes):
        """Test unwrapping nested list[dict[str, WrappedClass]]."""
        annotation = typing.List[typing.Dict[str, _impl_Foo]]
        expr = build_unwrap_expr(annotation, wrapped_classes, "data")
        # Should have nested comprehensions
        assert "for x in data" in expr
        assert ".items()" in expr
        assert "._impl_instance" in expr

    def test_primitive_no_unwrap(self, wrapped_classes):
        """Test that primitives are returned as-is."""
        expr = build_unwrap_expr(str, wrapped_classes, "text")
        assert expr == "text"

    def test_any_no_unwrap(self, wrapped_classes):
        """Test that typing.Any is not unwrapped."""
        expr = build_unwrap_expr(typing.Any, wrapped_classes, "anything")
        assert expr == "anything"


class TestBuildWrapExpr:
    """Tests for build_wrap_expr()."""

    def test_direct_wrapped_type(self, wrapped_classes):
        """Test wrapping a direct wrapped type."""
        expr = build_wrap_expr(_impl_Foo, wrapped_classes, "result")
        assert expr == "Foo._from_impl(result)"

    def test_list_of_wrapped(self, wrapped_classes):
        """Test wrapping list[WrappedClass]."""
        annotation = typing.List[_impl_Bar]
        expr = build_wrap_expr(annotation, wrapped_classes, "items")
        assert "Bar._from_impl(x)" in expr
        assert "for x in items" in expr
        assert expr.startswith("[")

    def test_dict_with_wrapped_values(self, wrapped_classes):
        """Test wrapping dict[str, WrappedClass]."""
        annotation = typing.Dict[str, _impl_Foo]
        expr = build_wrap_expr(annotation, wrapped_classes, "mapping")
        assert "Foo._from_impl(v)" in expr
        assert ".items()" in expr
        assert "{" in expr

    def test_optional_wrapped_type(self, wrapped_classes):
        """Test wrapping Optional[WrappedClass]."""
        annotation = typing.Optional[_impl_Bar]
        expr = build_wrap_expr(annotation, wrapped_classes, "maybe_val")
        assert "Bar._from_impl(maybe_val)" in expr
        assert "if maybe_val is not None else None" in expr

    def test_tuple_of_wrapped(self, wrapped_classes):
        """Test wrapping tuple[WrappedClass, ...]."""
        annotation = typing.Tuple[_impl_Foo, ...]
        expr = build_wrap_expr(annotation, wrapped_classes, "tup")
        assert "Foo._from_impl(x)" in expr
        assert "tuple(" in expr
        assert "for x in tup" in expr

    def test_nested_list_dict(self, wrapped_classes):
        """Test wrapping nested list[dict[str, WrappedClass]]."""
        annotation = typing.List[typing.Dict[str, _impl_Bar]]
        expr = build_wrap_expr(annotation, wrapped_classes, "data")
        # Should have nested comprehensions
        assert "Bar._from_impl(v)" in expr
        assert "for x in data" in expr
        assert ".items()" in expr

    def test_primitive_no_wrap(self, wrapped_classes):
        """Test that primitives are returned as-is."""
        expr = build_wrap_expr(int, wrapped_classes, "number")
        assert expr == "number"

    def test_any_no_wrap(self, wrapped_classes):
        """Test that typing.Any is not wrapped."""
        expr = build_wrap_expr(typing.Any, wrapped_classes, "anything")
        assert expr == "anything"


class TestEdgeCases:
    """Tests for edge cases and complex scenarios."""

    def test_multiple_wrapped_classes_in_dict(self, wrapped_classes):
        """Test dict with multiple wrapped classes doesn't break."""
        # dict[Foo, Bar] would be unusual but should handle gracefully
        annotation = typing.Dict[_impl_Foo, _impl_Bar]
        # This should at least not crash
        needs_translation(annotation, wrapped_classes)
        # Keys are not translated, only values
        expr = build_wrap_expr(annotation, wrapped_classes, "data")
        # Should still work but only translate values
        assert "._from_impl(" in expr or expr == "data"

    def test_deeply_nested_structure(self, wrapped_classes):
        """Test deeply nested type structure."""
        annotation = typing.List[typing.Optional[typing.Dict[str, _impl_Foo]]]
        expr = build_unwrap_expr(annotation, wrapped_classes, "deep")
        # Should handle deep nesting
        assert "._impl_instance" in expr

    def test_empty_wrapped_classes(self):
        """Test with no wrapped classes."""
        empty_wrapped = {}
        assert needs_translation(_impl_Foo, empty_wrapped) is False
        expr = build_unwrap_expr(_impl_Foo, empty_wrapped, "val")
        assert expr == "val"  # No translation without mapping
