"""Utilities for parsing and formatting function/method signatures."""

import collections.abc
import inspect


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
