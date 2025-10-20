"""Type translation utilities for converting between wrapper and implementation types."""

import inspect
import typing


def format_type_annotation(annotation) -> str:
    """Format a type annotation for code generation."""
    if annotation is type(None):
        return "None"

    # Handle string annotations (forward references)
    if isinstance(annotation, str):
        # Return the string as-is - quotes will be added later if needed
        return annotation

    # Handle ForwardRef specially
    if hasattr(annotation, "__forward_arg__"):
        # This is a ForwardRef - return the string it contains without quotes
        # Quotes will be added later if needed during code generation
        return annotation.__forward_arg__

    if hasattr(annotation, "__origin__"):
        # This is a generic type like list[str], dict[str, int], etc.
        # Need to recursively format args to handle ForwardRef within generics
        origin = annotation.__origin__
        args = typing.get_args(annotation)

        if args:
            # Format each argument recursively
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
            return repr(annotation).replace("typing.", "typing.")
    elif hasattr(annotation, "__module__") and hasattr(annotation, "__name__"):
        if annotation.__module__ in ("builtins", "__builtin__"):
            return annotation.__name__
        else:
            return f"{annotation.__module__}.{annotation.__name__}"
    else:
        return repr(annotation)


def get_wrapped_classes(wrapped_items: dict) -> dict[str, str]:
    """
    Extract mapping of wrapped class names to their fully-qualified implementation names.

    Args:
        wrapped_items: Dict mapping original objects to (target_module, target_name) tuples

    Returns:
        Dict mapping wrapper class name to implementation qualified name.
        Example: {"Bar": "_my_library.Bar", "Baz": "_my_library.Baz"}
    """
    wrapped = {}
    for obj, (target_module, target_name) in wrapped_items.items():
        if isinstance(obj, type):  # It's a class
            impl_qualified = f"{obj.__module__}.{obj.__name__}"
            wrapped[target_name] = impl_qualified
    return wrapped


def translate_type_annotation(annotation, wrapped_classes: dict[str, str], impl_module: str) -> tuple[str, str]:
    """
    Translate type annotation from implementation types to wrapper types.

    Args:
        annotation: The type annotation to translate
        wrapped_classes: Mapping of wrapper names to impl qualified names
        impl_module: The implementation module name (e.g., "_my_library")

    Returns:
        Tuple of (wrapper_type_str, impl_type_str) as formatted strings

    Examples:
        _my_library.Bar -> ("Bar", "_my_library.Bar")
        list[_my_library.Bar] -> ("list[Bar]", "list[_my_library.Bar]")
        str -> ("str", "str")  # no translation needed
        typing.Any -> ("typing.Any", "typing.Any")  # no translation
        "Node" -> ("Node", "_my_library.Node")  # string annotation
    """
    # Handle string annotations specially
    if isinstance(annotation, str):
        # Check if this string is a wrapped class name
        for wrapper_name, impl_qualified in wrapped_classes.items():
            if annotation == wrapper_name:
                # It's a direct reference to a wrapped class
                return wrapper_name, impl_qualified
        # Not a wrapped class, return as-is
        return annotation, annotation

    # Format the annotation to get string representation
    impl_str = format_type_annotation(annotation)
    wrapper_str = impl_str

    # Replace each wrapped class reference
    for wrapper_name, impl_qualified in wrapped_classes.items():
        # Replace fully qualified name (e.g., "_my_library.Bar" -> "Bar")
        wrapper_str = wrapper_str.replace(impl_qualified, wrapper_name)

    return wrapper_str, impl_str


def needs_translation(annotation, wrapped_classes: dict[str, str]) -> bool:
    """
    Check if a type annotation contains any wrapped class types that need translation.

    Args:
        annotation: The type annotation to check
        wrapped_classes: Mapping of wrapper names to impl qualified names

    Returns:
        True if the annotation contains at least one wrapped class type
    """
    if annotation == inspect.Signature.empty:
        return False

    # Handle string annotations (forward references)
    if isinstance(annotation, str):
        # Check if the string matches any wrapped class name
        for wrapper_name in wrapped_classes.keys():
            if wrapper_name in annotation:
                return True
        return False

    impl_str = format_type_annotation(annotation)

    # Check if any wrapped class appears in the type string
    # Need to check both wrapper names and impl qualified names
    for wrapper_name, impl_qualified in wrapped_classes.items():
        if impl_qualified in impl_str or wrapper_name in impl_str:
            return True

    return False


def build_unwrap_expr(annotation, wrapped_classes: dict[str, str], var_name: str = "value") -> str:
    """
    Build Python expression to unwrap a value from wrapper type to implementation type.

    This generates annotation-driven unwrapping code that extracts ._impl_instance
    from wrapper objects.

    Args:
        annotation: The type annotation
        wrapped_classes: Mapping of wrapper names to impl qualified names
        var_name: The variable name to unwrap (default: "value")

    Returns:
        Python expression string that unwraps the value

    Examples:
        Bar -> "value._impl_instance"
        list[Bar] -> "[x._impl_instance for x in value]"
        dict[str, Bar] -> "{k: v._impl_instance for k, v in value.items()}"
        Optional[Bar] -> "value._impl_instance if value is not None else None"
        str -> "value"  # no unwrapping needed
    """
    if not needs_translation(annotation, wrapped_classes):
        return var_name

    # Get the origin and args for generic types
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is None:
        # Direct wrapped class type
        return f"{var_name}._impl_instance"

    elif origin is list:
        if args:
            inner_expr = build_unwrap_expr(args[0], wrapped_classes, "x")
            return f"[{inner_expr} for x in {var_name}]"
        return var_name

    elif origin is dict:
        if len(args) >= 2:
            value_expr = build_unwrap_expr(args[1], wrapped_classes, "v")
            if value_expr != "v":
                return f"{{k: {value_expr} for k, v in {var_name}.items()}}"
        return var_name

    elif origin is tuple:
        if args:
            inner_expr = build_unwrap_expr(args[0], wrapped_classes, "x")
            if inner_expr != "x":
                return f"tuple({inner_expr} for x in {var_name})"
        return var_name

    elif origin is typing.Union:
        # Handle Optional[T] which is Union[T, None]
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            inner_expr = build_unwrap_expr(non_none_args[0], wrapped_classes, var_name)
            if inner_expr != var_name:
                return f"{inner_expr} if {var_name} is not None else None"
        return var_name

    return var_name


def build_wrap_expr(
    annotation,
    wrapped_classes: dict[str, str],
    var_name: str = "value",
    local_wrapped_classes: dict[str, str] = None,
    cross_module_imports: dict[str, set[str]] = None,
) -> str:
    """
    Build Python expression to wrap a value from implementation type to wrapper type.

    This generates annotation-driven wrapping code that calls ClassName._from_impl()
    classmethods, using either local references or fully qualified module paths.

    Args:
        annotation: The type annotation
        wrapped_classes: Mapping of ALL wrapper names to impl qualified names
        var_name: The variable name to wrap (default: "value")
        local_wrapped_classes: Mapping of wrapper names defined in the current module.
                              If None, assumes all classes are local.
        cross_module_imports: Dict mapping target modules to sets of imported class names.
                             Used to generate fully qualified references.

    Returns:
        Python expression string that wraps the value

    Examples:
        Local Bar -> "Bar._from_impl(value)"
        Cross-module Bar from foo.bar -> "foo.bar.Bar._from_impl(value)"
        list[Bar] -> "[Bar._from_impl(x) for x in value]" (if local)
        Optional[Bar] -> "Bar._from_impl(value) if value is not None else None" (if local)
        str -> "value"  # no wrapping needed
    """
    if not needs_translation(annotation, wrapped_classes):
        return var_name

    # If local_wrapped_classes not specified, assume all are local
    if local_wrapped_classes is None:
        local_wrapped_classes = wrapped_classes

    if cross_module_imports is None:
        cross_module_imports = {}

    # Build reverse lookup: class_name -> module_name
    class_to_module = {}
    for module_name, class_names in cross_module_imports.items():
        for class_name in class_names:
            class_to_module[class_name] = module_name

    def _get_wrap_call(wrapper_name: str, value: str) -> str:
        """Get the appropriate wrap call based on whether class is local or cross-module."""
        if wrapper_name in local_wrapped_classes:
            # Local class - use simple reference
            return f"{wrapper_name}._from_impl({value})"
        elif wrapper_name in class_to_module:
            # Cross-module class - use fully qualified reference
            module_name = class_to_module[wrapper_name]
            return f"{module_name}.{wrapper_name}._from_impl({value})"
        else:
            # Fallback - assume local
            return f"{wrapper_name}._from_impl({value})"

    # Handle string annotations (forward references)
    if isinstance(annotation, str):
        # Check if it matches a wrapped class name
        for wrapper_name in wrapped_classes.keys():
            if annotation == wrapper_name or annotation == f"'{wrapper_name}'":
                return _get_wrap_call(wrapper_name, var_name)
        return var_name

    # Get the origin and args for generic types
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is None:
        # Direct wrapped class type - need to find the wrapper name
        impl_str = format_type_annotation(annotation)
        for wrapper_name, impl_qualified in wrapped_classes.items():
            if impl_str == impl_qualified or impl_str.strip("'\"") == wrapper_name:
                return _get_wrap_call(wrapper_name, var_name)
        return var_name

    elif origin is list:
        if args:
            inner_expr = build_wrap_expr(args[0], wrapped_classes, "x", local_wrapped_classes, cross_module_imports)
            if inner_expr != "x":
                return f"[{inner_expr} for x in {var_name}]"
        return var_name

    elif origin is dict:
        if len(args) >= 2:
            value_expr = build_wrap_expr(args[1], wrapped_classes, "v", local_wrapped_classes, cross_module_imports)
            if value_expr != "v":
                return f"{{k: {value_expr} for k, v in {var_name}.items()}}"
        return var_name

    elif origin is tuple:
        if args:
            inner_expr = build_wrap_expr(args[0], wrapped_classes, "x", local_wrapped_classes, cross_module_imports)
            if inner_expr != "x":
                return f"tuple({inner_expr} for x in {var_name})"
        return var_name

    elif origin is typing.Union:
        # Handle Optional[T] which is Union[T, None]
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            inner_expr = build_wrap_expr(
                non_none_args[0], wrapped_classes, var_name, local_wrapped_classes, cross_module_imports
            )
            if inner_expr != var_name:
                return f"{inner_expr} if {var_name} is not None else None"
        return var_name

    return var_name
