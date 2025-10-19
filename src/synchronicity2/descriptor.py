"""
Generic infrastructure for wrapped methods and functions.

This module provides:
- WrappedMethodDescriptor: A descriptor for class methods that provides sync/async variants
- wrapped_method: Decorator for wrapping class methods
- wrapped_function: Decorator for wrapping module-level functions

Both patterns allow calling the sync version directly (e.g., foo()) and the async version
via .aio() (e.g., foo.aio()).
"""

import typing

T = typing.TypeVar("T")


class WrappedMethodDescriptor(typing.Generic[T]):
    """Descriptor that provides both sync and async method variants via .aio()"""

    method_wrapper_type: type[T]
    unbound_impl_method: typing.Callable[..., typing.Any]
    sync_wrapper_method: typing.Callable[..., typing.Any]

    def __init__(self, method_wrapper_type, unbound_impl_method, sync_wrapper_method):
        self.method_wrapper_type = method_wrapper_type
        self.unbound_impl_method = unbound_impl_method
        self.sync_wrapper_method = sync_wrapper_method

    def __get__(self, wrapper_instance, owner) -> T:
        if wrapper_instance is None:
            # For class access or module-level functions, return self to allow descriptor access
            return self

        return self.method_wrapper_type(wrapper_instance, self.sync_wrapper_method)




def wrapped_method(unbound_impl_method, method_wrapper_type: type[T]):
    """
    Decorator that creates a WrappedMethodDescriptor for a method.

    Args:
        unbound_impl_method: The original async implementation method
        method_wrapper_type: The wrapper class that provides sync and async variants

    Returns:
        A WrappedMethodDescriptor that will create method_wrapper_type instances
    """

    def decorator(sync_wrapper_method) -> WrappedMethodDescriptor[T]:
        return WrappedMethodDescriptor(method_wrapper_type, unbound_impl_method, sync_wrapper_method)

    return decorator


def wrapped_function(unbound_impl_function, function_wrapper_type: type[T]):
    """
    Decorator that creates a wrapper instance for a module-level function.

    Args:
        unbound_impl_function: The original async implementation function
        function_wrapper_type: The wrapper class that provides sync and async variants

    Returns:
        An instance of function_wrapper_type that wraps the sync function
    """

    def decorator(sync_wrapper_function) -> T:
        return function_wrapper_type(sync_wrapper_function)

    return decorator
