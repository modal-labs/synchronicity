"""Utilities for parsing and formatting function/method signatures."""

import collections.abc
import inspect
import typing


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


def returns_awaitable(return_annotation) -> bool:
    """
    Check if a return type annotation represents an awaitable type.

    This includes Coroutine, Awaitable, and similar async types.
    A sync function that returns one of these types should be treated
    as async for wrapping purposes.

    Args:
        return_annotation: The return type annotation

    Returns:
        True if the return type is an awaitable type
    """
    if return_annotation == inspect.Signature.empty:
        return False

    # Check for common awaitable types
    awaitable_origins = (
        collections.abc.Coroutine,
        collections.abc.Awaitable,
    )

    # Check if the annotation has an __origin__ attribute (generic types)
    if hasattr(return_annotation, "__origin__"):
        return return_annotation.__origin__ in awaitable_origins

    # Check if the annotation itself is one of the awaitable types
    # This handles cases like typing.Coroutine or typing.Awaitable
    if return_annotation in awaitable_origins:
        return True

    # Check typing module types (Coroutine, Awaitable)
    try:
        if hasattr(typing, "get_origin"):
            origin = typing.get_origin(return_annotation)
            if origin in awaitable_origins:
                return True
    except Exception:
        pass

    return False
