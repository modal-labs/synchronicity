"""Code generation package for synchronicity2."""

# Re-export all public functions for backward compatibility
from .signature_utils import format_return_types, is_async_generator, parse_parameters
from .type_translation import (
    build_unwrap_expr,
    build_wrap_expr,
    format_return_annotation_with_translation,
    format_type_annotation,
    format_type_for_annotation,
    needs_translation,
)

__all__ = [
    # Type translation
    "format_type_annotation",  # Simple formatting without translation
    "format_type_for_annotation",  # With wrapper/impl translation
    "format_return_annotation_with_translation",  # Complete return type formatting with translation
    "needs_translation",
    "build_unwrap_expr",
    "build_wrap_expr",
    # Signature utilities
    "parse_parameters",
    "is_async_generator",
    "format_return_types",
]
