"""Utilities for parsing and formatting function/method signatures."""

import collections.abc
import inspect

from .type_translation import format_type_annotation


def parse_parameters(sig: inspect.Signature, skip_self: bool = False) -> tuple[str, str, list[str]]:
    """
    Parse function/method parameters into formatted strings.

    Args:
        sig: The function signature
        skip_self: If True, skip 'self' parameter (for methods)

    Returns:
        Tuple of (params_str, call_args_str, call_args_list):
        - params_str: Comma-separated parameter declarations with types
        - call_args_str: Comma-separated parameter names for calls
        - call_args_list: List of parameter names
    """
    params = []
    call_args = []

    for name, param in sig.parameters.items():
        if skip_self and name == "self":
            continue

        param_str = name
        if param.annotation != param.empty:
            annotation_str = format_type_annotation(param.annotation)
            param_str += f": {annotation_str}"

        if param.default is not param.empty:
            default_val = repr(param.default)
            param_str += f" = {default_val}"

        params.append(param_str)
        call_args.append(name)

    params_str = ", ".join(params)
    call_args_str = ", ".join(call_args)

    return params_str, call_args_str, call_args


def is_async_generator(func_or_method, return_annotation) -> bool:
    """
    Check if a callable is an async generator.

    Args:
        func_or_method: The function or method to check
        return_annotation: The return type annotation

    Returns:
        True if the callable is an async generator
    """
    # First check using inspect
    if inspect.isasyncgenfunction(func_or_method):
        return True

    # Also check return annotation
    if return_annotation != inspect.Signature.empty:
        return (
            hasattr(return_annotation, "__origin__") and return_annotation.__origin__ is collections.abc.AsyncGenerator
        )

    return False


def format_return_types(return_annotation, is_async_gen: bool) -> tuple[str, str]:
    """
    Format sync and async return type strings.

    Args:
        return_annotation: The return type annotation from the function signature
        is_async_gen: Whether the function is an async generator

    Returns:
        Tuple of (sync_return_str, async_return_str) including " -> " prefix,
        or empty strings if no return annotation
    """
    if return_annotation == inspect.Signature.empty:
        if is_async_gen:
            return " -> typing.Generator", " -> typing.AsyncGenerator"
        else:
            return "", ""

    # Handle different return types
    if is_async_gen:
        # For async generators, sync version returns Generator[T, None, None],
        # async version returns AsyncGenerator[T, None]
        if hasattr(return_annotation, "__args__") and return_annotation.__args__:
            # Extract the yielded type from AsyncGenerator[T, Send]
            yield_type = return_annotation.__args__[0]
            yield_type_str = format_type_annotation(yield_type)
            sync_return_annotation = f"typing.Generator[{yield_type_str}, None, None]"

            # For async generators, also extract the send type (usually None) for proper typing
            if len(return_annotation.__args__) > 1:
                send_type = return_annotation.__args__[1]
                send_type_str = format_type_annotation(send_type)
                async_return_annotation = f"typing.AsyncGenerator[{yield_type_str}, {send_type_str}]"
            else:
                async_return_annotation = f"typing.AsyncGenerator[{yield_type_str}]"
        else:
            sync_return_annotation = "typing.Generator"
            async_return_annotation = "typing.AsyncGenerator"
    else:
        # For regular async functions
        sync_return_annotation = format_type_annotation(return_annotation)
        async_return_annotation = sync_return_annotation

    sync_return_str = f" -> {sync_return_annotation}"
    async_return_str = f" -> {async_return_annotation}"

    return sync_return_str, async_return_str
