"""Code generation functions for creating wrapper classes and functions."""

import inspect
import sys
import types

from .signature_utils import format_return_types, is_async_generator, parse_parameters
from .type_translation import (
    build_unwrap_expr,
    build_wrap_expr,
    format_type_annotation,
    get_wrapped_classes,
    needs_translation,
    translate_type_annotation,
)


def generate_wrapper_helpers(wrapped_classes: dict[str, str], impl_module: str) -> str:
    """
    Generate wrapper helper functions for each wrapped class.

    Each helper maintains a WeakValueDictionary cache to preserve identity
    (same impl instance always returns the same wrapper instance).

    Args:
        wrapped_classes: Mapping of wrapper names to impl qualified names
        impl_module: The implementation module name

    Returns:
        String containing all wrapper helper function definitions
    """
    if not wrapped_classes:
        return ""

    helpers = []

    # Import weakref
    helpers.append("import weakref")
    helpers.append("")

    # Generate a helper for each wrapped class
    for wrapper_name, impl_qualified in wrapped_classes.items():
        helper_code = f"""# Wrapper cache for {wrapper_name} to preserve identity
_cache_{wrapper_name}: weakref.WeakValueDictionary = weakref.WeakValueDictionary()

def _wrap_{wrapper_name}(impl_instance: {impl_qualified}) -> "{wrapper_name}":
    \"\"\"Wrap an implementation instance, preserving identity via weak reference cache.\"\"\"
    # Use id() as cache key since impl instances are Python objects
    cache_key = id(impl_instance)

    # Check cache first
    if cache_key in _cache_{wrapper_name}:
        return _cache_{wrapper_name}[cache_key]

    # Create new wrapper using __new__ to bypass __init__
    wrapper = {wrapper_name}.__new__({wrapper_name})
    wrapper._impl_instance = impl_instance

    # Cache it
    _cache_{wrapper_name}[cache_key] = wrapper

    return wrapper"""
        helpers.append(helper_code)

    return "\n\n".join(helpers)


