"""Code generation package for synchronicity2."""

# Re-export all public functions for backward compatibility
from .signature_utils import format_return_types, is_async_generator, parse_parameters
from .type_translation import (
    build_unwrap_expr,
    build_wrap_expr,
    format_type_annotation,
    get_wrapped_classes,
    needs_translation,
    translate_type_annotation,
)

__all__ = [
    # Type translation
    "format_type_annotation",
    "get_wrapped_classes",
    "translate_type_annotation",
    "needs_translation",
    "build_unwrap_expr",
    "build_wrap_expr",
    # Signature utilities
    "parse_parameters",
    "is_async_generator",
    "format_return_types",
]
