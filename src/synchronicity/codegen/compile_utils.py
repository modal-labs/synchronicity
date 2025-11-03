"""Utility functions for code generation."""

from __future__ import annotations

import inspect
import sys
import types
import typing

from .type_transformer import create_transformer


def _safe_get_annotations(obj, globals_dict=None):
    """
    Safely get annotations, with fallback for forward references under TYPE_CHECKING.

    For forward references that can't be resolved (NameError), we try to import the
    module from fully qualified names (e.g., "my_mod.SomeType").
    """
    try:
        return inspect.get_annotations(obj, eval_str=True, globals=globals_dict)
    except NameError:
        # Forward reference can't be resolved - try importing from qualified names
        # Get raw string annotations
        raw_annotations = inspect.get_annotations(obj, eval_str=False, globals=globals_dict)

        # Build an extended globals dict with imports for qualified names
        extended_globals = (globals_dict or {}).copy()

        for key, annotation_str in raw_annotations.items():
            if isinstance(annotation_str, str) and "." in annotation_str:
                # Extract module path from qualified name (e.g., "my_mod.sub.SomeType" -> "my_mod.sub")
                parts = annotation_str.split(".")
                if len(parts) >= 2:
                    # Import the full module path (all parts except the last, which is the class name)
                    module_path = ".".join(parts[:-1])
                    try:
                        # Try to import the module
                        import importlib

                        importlib.import_module(module_path)
                        # Add the top-level module to extended_globals
                        # For "a.b.c.Class", add "a" -> sys.modules["a"]
                        top_level_module = parts[0]
                        if top_level_module not in extended_globals:
                            extended_globals[top_level_module] = sys.modules.get(top_level_module)
                    except ImportError:
                        pass  # Skip if module can't be imported

        # Try again with extended globals
        try:
            return inspect.get_annotations(obj, eval_str=True, globals=extended_globals)
        except (NameError, AttributeError):
            # Still can't resolve - return string annotations
            return raw_annotations


def _contains_self_type(annotation) -> bool:
    """Check if a type annotation contains typing.Self.

    Args:
        annotation: Type annotation to check

    Returns:
        True if typing.Self is found anywhere in the annotation
    """
    # Check for typing.Self directly
    if annotation is typing.Self:
        return True

    # Check for generic types with typing.Self as an argument
    origin = typing.get_origin(annotation)
    if origin is not None:
        args = typing.get_args(annotation)
        for arg in args:
            if _contains_self_type(arg):
                return True

    return False


def _extract_typevars_from_annotation(annotation, collected: dict[str, typing.TypeVar | typing.ParamSpec]) -> None:
    """Recursively extract TypeVar and ParamSpec instances from a type annotation.

    Args:
        annotation: Type annotation to extract from
        collected: Dict to store found typevars (name -> typevar instance)
    """
    # Handle TypeVar and ParamSpec directly
    if isinstance(annotation, typing.TypeVar):
        collected[annotation.__name__] = annotation
        return
    if isinstance(annotation, typing.ParamSpec):
        collected[annotation.__name__] = annotation
        return

    # Recursively process generic types
    args = typing.get_args(annotation)

    if args:
        for arg in args:
            _extract_typevars_from_annotation(arg, collected)


def _extract_typevars_from_function(
    f: types.FunctionType, annotations: dict[str, typing.Any]
) -> dict[str, typing.TypeVar | typing.ParamSpec]:
    """Extract all TypeVar and ParamSpec instances used in a function's signature.

    Args:
        f: The function to extract from
        annotations: Resolved annotations dict from inspect.get_annotations

    Returns:
        Dict mapping typevar name to typevar instance
    """
    collected: dict[str, typing.TypeVar | typing.ParamSpec] = {}

    # Extract from all annotations (parameters and return type)
    for annotation in annotations.values():
        _extract_typevars_from_annotation(annotation, collected)

    return collected


def _parse_parameters_with_transformers(
    sig: inspect.Signature,
    annotations: dict,
    synchronized_types: dict[type, tuple[str, str]],
    synchronizer_name: str,
    current_target_module: str,
    skip_first_param: bool = False,
    unwrap_indent: str = "    ",
) -> tuple[str, str, str]:
    """
    Parse function parameters and generate wrapper parameter list, call arguments, and unwrap code.

    Args:
        sig: Function signature
        annotations: Resolved annotations from inspect.get_annotations
        synchronized_types: Dict mapping implementation types to (target_module, wrapper_name)
        synchronizer_name: Name of the synchronizer
        current_target_module: Current target module
        skip_first_param: Whether to skip the first parameter (for instance/class methods)
        unwrap_indent: Indentation for unwrap statements

    Returns:
        Tuple of (param_str, call_args_str, unwrap_code):
        - param_str: Parameter list for wrapper function
        - call_args_str: Arguments to pass to implementation function
        - unwrap_code: Code to unwrap wrapper arguments to implementation arguments
    """
    params = []
    call_args = []
    unwrap_stmts = []

    # Track if we need to add positional-only marker (/)
    last_positional_only_index = -1
    positional_only_marker_added = False

    for i, (name, param) in enumerate(sig.parameters.items()):
        # Skip first parameter if requested (self/cls in methods)
        if i == 0 and skip_first_param:
            continue

        param_annotation = annotations.get(name, param.annotation)

        # Create transformer for this parameter
        transformer = create_transformer(param_annotation, synchronized_types)

        # Track positional-only parameters
        if param.kind == inspect.Parameter.POSITIONAL_ONLY:
            last_positional_only_index = len(params)

        # Handle VAR_POSITIONAL (*args) and VAR_KEYWORD (**kwargs)
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            # *args
            if param_annotation != param.empty:
                wrapper_type_str = transformer.wrapped_type(synchronized_types, current_target_module)
                params.append(f"*{name}: {wrapper_type_str}")
            else:
                params.append(f"*{name}")
            call_args.append(f"*{name}")

        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            # **kwargs
            if param_annotation != param.empty:
                wrapper_type_str = transformer.wrapped_type(synchronized_types, current_target_module)
                params.append(f"**{name}: {wrapper_type_str}")
            else:
                params.append(f"**{name}")
            call_args.append(f"**{name}")

        elif param.kind == inspect.Parameter.KEYWORD_ONLY:
            # Keyword-only parameter
            if param_annotation != param.empty:
                wrapper_type_str = transformer.wrapped_type(synchronized_types, current_target_module)
                param_str = f"{name}: {wrapper_type_str}"

                # Generate unwrap code if needed
                if transformer.needs_translation():
                    unwrap_expr = transformer.unwrap_expr(synchronized_types, name)
                    unwrap_stmts.append(f"{unwrap_indent}{name}_impl = {unwrap_expr}")
                    call_args.append(f"{name}={name}_impl")
                else:
                    call_args.append(f"{name}={name}")
            else:
                param_str = name
                call_args.append(f"{name}={name}")

            # Handle default values
            if param.default is not param.empty:
                default_val = repr(param.default)
                param_str += f" = {default_val}"

            params.append(param_str)

        else:
            # Handle regular parameters (POSITIONAL_ONLY, POSITIONAL_OR_KEYWORD)
            if param_annotation != param.empty:
                wrapper_type_str = transformer.wrapped_type(synchronized_types, current_target_module)
                param_str = f"{name}: {wrapper_type_str}"

                # Generate unwrap code if needed
                if transformer.needs_translation():
                    unwrap_expr = transformer.unwrap_expr(synchronized_types, name)
                    unwrap_stmts.append(f"{unwrap_indent}{name}_impl = {unwrap_expr}")
                    call_args.append(f"{name}_impl")
                else:
                    call_args.append(name)
            else:
                param_str = name
                call_args.append(name)

            # Handle default values
            if param.default is not param.empty:
                default_val = repr(param.default)
                param_str += f" = {default_val}"

            params.append(param_str)

        # Add positional-only marker after last POSITIONAL_ONLY parameter
        if not positional_only_marker_added and last_positional_only_index >= 0:
            if (
                param.kind != inspect.Parameter.POSITIONAL_ONLY
                and param.kind != inspect.Parameter.VAR_POSITIONAL
                and len(params) > last_positional_only_index
            ):
                # Insert the / marker after the last positional-only parameter
                params.insert(last_positional_only_index + 1, "/")
                positional_only_marker_added = True

    param_str = ", ".join(params)
    call_args_str = ", ".join(call_args)

    # Build unwrap code block
    unwrap_code = "\n".join(unwrap_stmts) if unwrap_stmts else ""

    return param_str, call_args_str, unwrap_code


def _build_call_with_wrap(
    call_expr: str,
    return_transformer,
    synchronized_types: dict[type, tuple[str, str]],
    synchronizer_name: str,
    current_target_module: str,
    indent: str = "    ",
    is_async: bool = True,
    *,
    is_function: bool = False,
) -> str:
    """
    Build a function call with optional return value wrapping.

    This is used for non-generator return types. Nested generators inside
    return values (e.g., tuple[AsyncGenerator, ...]) are properly wrapped
    according to the is_async context.

    Args:
        call_expr: The function call expression
        return_transformer: TypeTransformer for the return type
        synchronized_types: Dict mapping implementation types to (target_module, wrapper_name)
        synchronizer_name: Name of the synchronizer
        current_target_module: Current target module
        indent: Indentation string
        is_async: Whether this is an async context (affects generator wrapping)
        is_function: Whether this is for a module-level function (not a method). If True, strips 'self.' from wrap_expr.

    Returns:
        Code string with the call and optional wrapping
    """
    if return_transformer.needs_translation():
        wrap_expr = return_transformer.wrap_expr(synchronized_types, current_target_module, "result", is_async=is_async)
        # For module-level functions, strip 'self.' prefix from helper calls
        if is_function:
            wrap_expr = wrap_expr.replace("self.", "")
        return f"""{indent}result = {call_expr}
{indent}return {wrap_expr}"""
    else:
        return f"{indent}return {call_expr}"


def _format_return_annotation(
    return_transformer,
    synchronized_types: dict[type, tuple[str, str]],
    synchronizer_name: str,
    current_target_module: str,
) -> tuple[str, str]:
    """
    Format return type annotations for both sync and async versions.

    Args:
        return_transformer: TypeTransformer for the return type
        synchronizer: The Synchronizer instance
        current_target_module: Current target module

    Returns:
        Tuple of (sync_return_str, async_return_str) with " -> " prefix
    """
    # Get the wrapped types for both sync and async contexts
    sync_return_type = return_transformer.wrapped_type(synchronized_types, current_target_module, is_async=False)
    async_return_type = return_transformer.wrapped_type(synchronized_types, current_target_module, is_async=True)

    if not sync_return_type:
        return "", ""

    # Quote the entire type annotation if it contains wrapped types
    should_quote = return_transformer.needs_translation()
    if should_quote:
        sync_return_str = f' -> "{sync_return_type}"'
        async_return_str = f' -> "{async_return_type}"'
    else:
        sync_return_str = f" -> {sync_return_type}"
        async_return_str = f" -> {async_return_type}"

    return sync_return_str, async_return_str
