"""Type translation utilities for converting between wrapper and implementation types.

This module uses object-based type checking (via get_annotations with eval_str=True)
rather than string-based matching for robustness and simplicity.
"""

import inspect
import typing
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..synchronizer import Synchronizer


def _check_no_forward_ref(annotation) -> None:
    """
    Validate that an annotation is not a ForwardRef.

    ForwardRef objects indicate that get_annotations(eval_str=True) failed to resolve
    a type annotation, which prevents object-based type checking. This usually happens
    when users quote individual type arguments inside generics.

    Args:
        annotation: The type annotation to check

    Raises:
        TypeError: If annotation is a ForwardRef, with guidance on how to fix it
    """
    if hasattr(annotation, "__forward_arg__"):
        forward_str = annotation.__forward_arg__
        raise TypeError(
            f"Found unresolved forward reference '{forward_str}' in type annotation. "
            f"This usually happens when you quote a type inside a generic annotation like "
            f'typing.AsyncGenerator["{forward_str}", None]. Instead, quote the entire type annotation: '
            f'"typing.AsyncGenerator[{forward_str}, None]". This allows proper type resolution for '
            f"object-based type checking."
        )


def format_type_annotation(annotation) -> str:
    """
    Format a type annotation for code generation (simple version without translation).

    This is used by signature_utils for basic type formatting.
    For wrapper/impl translation, use format_type_for_annotation instead.
    """
    if annotation is type(None):
        return "None"

    if annotation == inspect.Signature.empty:
        return ""

    # Handle generic types
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is not None:
        # Recursively format args
        if args:
            formatted_args = [format_type_annotation(arg) for arg in args]

            # Get the origin name
            if hasattr(origin, "__name__"):
                origin_name = origin.__name__
            else:
                origin_name = str(origin)

            # Check if we need typing prefix
            if origin in (list, dict, tuple, set, frozenset):
                # Built-in types
                return f"{origin_name}[{', '.join(formatted_args)}]"
            else:
                # typing module types
                origin_str = repr(origin)
                if "typing." in origin_str:
                    origin_name = origin_str.split(".")[-1].rstrip("'>")
                return f"typing.{origin_name}[{', '.join(formatted_args)}]"
        else:
            return repr(annotation)

    # Direct type
    if isinstance(annotation, type):
        if annotation.__module__ in ("builtins", "__builtin__"):
            return annotation.__name__
        else:
            return f"{annotation.__module__}.{annotation.__name__}"

    # Fallback
    return repr(annotation)


def needs_translation(annotation, synchronizer: "Synchronizer") -> bool:
    """
    Check if a type annotation contains any wrapped class types that need translation.

    Uses object identity checks against synchronizer._wrapped dict.

    Args:
        annotation: The type annotation to check (resolved type object)
        synchronizer: The Synchronizer instance

    Returns:
        True if the annotation contains at least one wrapped class type

    Examples:
        Person (where Person in synchronizer._wrapped) -> True
        list[Person] -> True
        str -> False
        list[str] -> False
    """
    if annotation == inspect.Signature.empty:
        return False

    # Validate no ForwardRef (would prevent object-based checks)
    _check_no_forward_ref(annotation)

    # Direct type check - most common case
    if isinstance(annotation, type) and annotation in synchronizer._wrapped:
        return True

    # Recursive check for generic types
    args = typing.get_args(annotation)
    if args:
        return any(needs_translation(arg, synchronizer) for arg in args)

    return False


def build_unwrap_expr(annotation, synchronizer: "Synchronizer", var_name: str = "value") -> str:
    """
    Build Python expression to unwrap a value from wrapper type to implementation type.

    This generates annotation-driven unwrapping code that extracts ._impl_instance
    from wrapper objects.

    Args:
        annotation: The type annotation (resolved type object)
        synchronizer: The Synchronizer instance
        var_name: The variable name to unwrap (default: "value")

    Returns:
        Python expression string that unwraps the value

    Examples:
        Person -> "value._impl_instance"
        list[Person] -> "[x._impl_instance for x in value]"
        dict[str, Person] -> "{k: v._impl_instance for k, v in value.items()}"
        Optional[Person] -> "value._impl_instance if value is not None else None"
        str -> "value"  # no unwrapping needed
    """
    if not needs_translation(annotation, synchronizer):
        return var_name

    # ForwardRef should have been caught by needs_translation
    # If we get here, something is wrong - validate again to provide clear error
    _check_no_forward_ref(annotation)

    # Get the origin and args for generic types
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is None:
        # Direct wrapped class type
        if isinstance(annotation, type) and annotation in synchronizer._wrapped:
            return f"{var_name}._impl_instance"
        return var_name

    elif origin is list:
        if args:
            inner_expr = build_unwrap_expr(args[0], synchronizer, "x")
            if inner_expr != "x":
                return f"[{inner_expr} for x in {var_name}]"
        return var_name

    elif origin is dict:
        if len(args) >= 2:
            value_expr = build_unwrap_expr(args[1], synchronizer, "v")
            if value_expr != "v":
                return f"{{k: {value_expr} for k, v in {var_name}.items()}}"
        return var_name

    elif origin is tuple:
        if args:
            inner_expr = build_unwrap_expr(args[0], synchronizer, "x")
            if inner_expr != "x":
                return f"tuple({inner_expr} for x in {var_name})"
        return var_name

    elif origin is typing.Union:
        # Handle Optional[T] which is Union[T, None]
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            inner_expr = build_unwrap_expr(non_none_args[0], synchronizer, var_name)
            if inner_expr != var_name:
                return f"{inner_expr} if {var_name} is not None else None"
        return var_name

    return var_name


def build_wrap_expr(
    annotation,
    synchronizer: "Synchronizer",
    current_target_module: str,
    var_name: str = "value",
) -> str:
    """
    Build Python expression to wrap a value from implementation type to wrapper type.

    This generates annotation-driven wrapping code that calls ClassName._from_impl()
    classmethods, using either local references or fully qualified module paths.

    Args:
        annotation: The type annotation (resolved type object)
        synchronizer: The Synchronizer instance
        current_target_module: The target module being compiled (for local vs cross-module determination)
        var_name: The variable name to wrap (default: "value")

    Returns:
        Python expression string that wraps the value

    Examples:
        Local Person -> "Person._from_impl(value)"
        Cross-module Person from foo.bar -> "foo.bar.Person._from_impl(value)"
        list[Person] -> "[Person._from_impl(x) for x in value]" (if local)
        Optional[Person] -> "Person._from_impl(value) if value is not None else None" (if local)
        str -> "value"  # no wrapping needed
    """
    if not needs_translation(annotation, synchronizer):
        return var_name

    def _get_wrap_call(type_obj: type, value: str) -> str:
        """Get the appropriate wrap call based on whether class is local or cross-module."""
        if type_obj in synchronizer._wrapped:
            target_module, wrapper_name = synchronizer._wrapped[type_obj]

            # Determine if local or cross-module
            if target_module == current_target_module:
                # Local class - use simple reference
                return f"{wrapper_name}._from_impl({value})"
            else:
                # Cross-module class - use fully qualified reference
                return f"{target_module}.{wrapper_name}._from_impl({value})"

        # Should not reach here if needs_translation returned True
        return value

    # ForwardRef should have been caught by needs_translation
    # If we get here, something is wrong - validate again to provide clear error
    _check_no_forward_ref(annotation)

    # Get the origin and args for generic types
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is None:
        # Direct wrapped class type
        if isinstance(annotation, type) and annotation in synchronizer._wrapped:
            return _get_wrap_call(annotation, var_name)
        return var_name

    elif origin is list:
        if args:
            inner_expr = build_wrap_expr(args[0], synchronizer, current_target_module, "x")
            if inner_expr != "x":
                return f"[{inner_expr} for x in {var_name}]"
        return var_name

    elif origin is dict:
        if len(args) >= 2:
            value_expr = build_wrap_expr(args[1], synchronizer, current_target_module, "v")
            if value_expr != "v":
                return f"{{k: {value_expr} for k, v in {var_name}.items()}}"
        return var_name

    elif origin is tuple:
        if args:
            inner_expr = build_wrap_expr(args[0], synchronizer, current_target_module, "x")
            if inner_expr != "x":
                return f"tuple({inner_expr} for x in {var_name})"
        return var_name

    elif origin is typing.Union:
        # Handle Optional[T] which is Union[T, None]
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            inner_expr = build_wrap_expr(non_none_args[0], synchronizer, current_target_module, var_name)
            if inner_expr != var_name:
                return f"{inner_expr} if {var_name} is not None else None"
        return var_name

    return var_name


def format_type_for_annotation(annotation, synchronizer: "Synchronizer", current_target_module: str) -> str:
    """
    Format a resolved type annotation for use in generated code.

    Converts type objects to string representations, using wrapper names instead of
    implementation names where appropriate, and applying proper module qualification.

    Args:
        annotation: The type annotation (resolved type object)
        synchronizer: The Synchronizer instance
        current_target_module: The target module being compiled

    Returns:
        String representation of the type for code generation

    Examples:
        Person (local) -> "Person"
        Person (cross-module from foo.bar) -> "foo.bar.Person"
        list[Person] -> "list[Person]"
        str -> "str"
        typing.Any -> "typing.Any"
    """
    if annotation is type(None):
        return "None"

    if annotation == inspect.Signature.empty:
        return ""

    # Validate no ForwardRef (would prevent object-based checks)
    _check_no_forward_ref(annotation)

    # Handle generic types
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is not None:
        # Recursively format args
        if args:
            formatted_args = [format_type_for_annotation(arg, synchronizer, current_target_module) for arg in args]

            # Get the origin name
            if hasattr(origin, "__name__"):
                origin_name = origin.__name__
            else:
                origin_name = str(origin)

            # Check if we need typing prefix
            if origin in (list, dict, tuple, set, frozenset):
                # Built-in types
                return f"{origin_name}[{', '.join(formatted_args)}]"
            else:
                # typing module types (Union, Optional, etc.)
                origin_str = repr(origin)
                if "typing." in origin_str:
                    origin_name = origin_str.split(".")[-1].rstrip("'>")
                return f"typing.{origin_name}[{', '.join(formatted_args)}]"
        else:
            return repr(annotation)

    # Direct type
    if isinstance(annotation, type):
        # Check if it's a wrapped type
        if annotation in synchronizer._wrapped:
            target_module, wrapper_name = synchronizer._wrapped[annotation]

            # Determine if local or cross-module
            if target_module == current_target_module:
                # Local - just use the name
                return wrapper_name
            else:
                # Cross-module - use fully qualified name
                return f"{target_module}.{wrapper_name}"

        # Not wrapped - format normally
        if annotation.__module__ in ("builtins", "__builtin__"):
            return annotation.__name__
        else:
            # For implementation types, use fully qualified name
            return f"{annotation.__module__}.{annotation.__name__}"

    # Fallback
    return repr(annotation)
