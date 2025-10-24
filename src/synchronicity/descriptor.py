"""
Generic infrastructure for wrapped methods and functions.

This module provides:
- WrappedMethodDescriptor: A descriptor for class methods that provides sync/async variants
- wrapped_method: Decorator for wrapping class methods
- replace_with: Decorator for swapping dummy function signatures with wrapper instances

The wrapped_method pattern allows calling the sync version directly (e.g., foo()) and the async version
via .aio() (e.g., foo.aio()).
"""

import typing

T = typing.TypeVar("T")


class WrappedMethodDescriptor(typing.Generic[T]):
    """Descriptor that provides both sync and async method variants via .aio()"""

    method_wrapper_type: type[T]

    def __init__(self, method_wrapper_type):
        self.method_wrapper_type = method_wrapper_type

    def __get__(self, wrapper_instance, owner) -> T:
        if wrapper_instance is None:
            # For class access, return self to allow descriptor access
            return self

        return self.method_wrapper_type(wrapper_instance)


def wrapped_method(method_wrapper_type: type[T]):
    """
    Decorator that creates a WrappedMethodDescriptor for a method.

    Args:
        method_wrapper_type: The wrapper class that provides sync and async variants

    Returns:
        A WrappedMethodDescriptor that will create method_wrapper_type instances
    """

    def decorator(_dummy_method) -> WrappedMethodDescriptor[T]:
        # The dummy method is ignored - the actual implementation is in the wrapper class
        return WrappedMethodDescriptor(method_wrapper_type)

    return decorator


def replace_with(wrapper: T) -> typing.Callable[[typing.Callable[..., typing.Any]], T]:
    """
    Decorator that replaces a dummy function signature with an actual wrapper instance.

    This is used to preserve full function signatures (including parameter names) for
    type checkers and go-to-definition, while swapping in the actual wrapper instance
    at runtime.

    Args:
        wrapper: The actual wrapper instance to use

    Returns:
        A decorator that ignores the dummy function and returns the wrapper

    Example:
        @replace_with(MyWrapper())
        def my_func(x: int, y: str) -> Result:
            # This dummy implementation is never called
            # It exists only for type checkers and IDE navigation
            return MyWrapper().__call__(x, y)
    """

    def decorator(_dummy_sync_signature: typing.Callable[..., typing.Any]) -> T:
        return wrapper

    return decorator
