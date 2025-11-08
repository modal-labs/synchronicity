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
    Check if a return type annotation represents a directly awaitable type.

    This includes Coroutine, Awaitable - types that need to be awaited directly.
    Does NOT include AsyncIterator/AsyncIterable which are objects that need wrapping but not awaiting.

    Args:
        return_annotation: The return type annotation

    Returns:
        True if the return type is a directly awaitable type
    """
    if return_annotation == inspect.Signature.empty:
        return False

    # Check for directly awaitable types (need to await the function call itself)
    awaitable_origins = (
        collections.abc.Coroutine,
        collections.abc.Awaitable,
    )

    # Check if the annotation has an __origin__ attribute (generic types)
    if hasattr(return_annotation, "__origin__"):
        return return_annotation.__origin__ in awaitable_origins

    # Check if the annotation itself is one of the awaitable types
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


def returns_async_iterable_type(return_annotation) -> bool:
    """
    Check if a return type is AsyncIterator or AsyncIterable.

    These types need both sync and async wrappers but don't need the function call itself to be awaited.

    Args:
        return_annotation: The return type annotation

    Returns:
        True if the return type is AsyncIterator or AsyncIterable
    """
    if return_annotation == inspect.Signature.empty:
        return False

    # Check for async iterable types
    async_iterable_origins = (
        collections.abc.AsyncIterator,
        collections.abc.AsyncIterable,
    )

    # Check if the annotation has an __origin__ attribute (generic types)
    if hasattr(return_annotation, "__origin__"):
        return return_annotation.__origin__ in async_iterable_origins

    # Check if the annotation itself is one of the types
    if return_annotation in async_iterable_origins:
        return True

    # Check typing module types
    try:
        if hasattr(typing, "get_origin"):
            origin = typing.get_origin(return_annotation)
            if origin in async_iterable_origins:
                return True
    except Exception:
        pass

    return False
