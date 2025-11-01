"""
Generic infrastructure for wrapped methods and functions.

This module provides:
- MethodWrapper: A generic wrapper class that provides both sync and async method variants
- WrappedMethodDescriptor: A descriptor for instance methods that provides sync/async variants
- WrappedClassMethodDescriptor: A descriptor for classmethods
- WrappedStaticMethodDescriptor: A descriptor for staticmethods
- wrapped_method: Decorator for wrapping instance methods
- wrapped_classmethod: Decorator for wrapping classmethods
- wrapped_staticmethod: Decorator for wrapping staticmethods
- replace_with: Decorator for swapping dummy function signatures with wrapper instances

The wrapped_method pattern allows calling the sync version directly (e.g., foo()) and the async version
via .aio() (e.g., foo.aio()).
"""

import typing
from typing import Any, Callable, Concatenate, ParamSpec, TypeVar, overload

T = TypeVar("T")
P = ParamSpec("P")
R = TypeVar("R")
AIO_P = ParamSpec("AIO_P")
AIO_R = TypeVar("AIO_R")


class MethodWrapper(typing.Generic[T, P, R, AIO_P, AIO_R]):
    """Generic wrapper class that provides both sync and async method variants via .aio()"""

    bound_instance: T
    sync_wrapper: Callable[Concatenate[T, P], R]
    aio_wrapper: Callable[Concatenate[T, AIO_P], AIO_R]

    def __init__(
        self,
        bound_instance: T,
        sync_wrapper: Callable[Concatenate[Any, P], R],
        aio_wrapper: Callable[Concatenate[Any, AIO_P], AIO_R],
    ):
        self.bound_instance = bound_instance
        self.sync_wrapper = sync_wrapper
        self.aio_wrapper = aio_wrapper

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return self.sync_wrapper(self.bound_instance, *args, **kwargs)

    def aio(self, *args: AIO_P.args, **kwargs: AIO_P.kwargs) -> AIO_R:
        return self.aio_wrapper(self.bound_instance, *args, **kwargs)


class ClassOrStaticMethodWrapper(typing.Generic[P, R, AIO_P, AIO_R]):
    """Generic wrapper class for classmethods and staticmethods with sync/async variants via .aio()"""

    bound_class: type
    sync_wrapper: Callable[Concatenate[type, P], R]
    aio_wrapper: Callable[Concatenate[type, AIO_P], AIO_R]

    def __init__(
        self,
        bound_class: type,
        sync_wrapper: Callable[Concatenate[type, P], R],
        aio_wrapper: Callable[Concatenate[type, AIO_P], AIO_R],
    ):
        self.bound_class = bound_class
        self.sync_wrapper = sync_wrapper
        self.aio_wrapper = aio_wrapper

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return self.sync_wrapper(self.bound_class, *args, **kwargs)

    def aio(self, *args: AIO_P.args, **kwargs: AIO_P.kwargs) -> AIO_R:
        return self.aio_wrapper(self.bound_class, *args, **kwargs)


class StaticMethodWrapper(typing.Generic[P, R, AIO_P, AIO_R]):
    """Generic wrapper class for staticmethods with sync/async variants via .aio()"""

    bound_class: type
    sync_wrapper: Callable[P, R]
    aio_wrapper: Callable[AIO_P, AIO_R]

    def __init__(
        self,
        bound_class: type,
        sync_wrapper: Callable[P, R],
        aio_wrapper: Callable[AIO_P, AIO_R],
    ):
        self.bound_class = bound_class
        self.sync_wrapper = sync_wrapper
        self.aio_wrapper = aio_wrapper

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return self.sync_wrapper(*args, **kwargs)

    def aio(self, *args: AIO_P.args, **kwargs: AIO_P.kwargs) -> AIO_R:
        return self.aio_wrapper(*args, **kwargs)


class WrappedMethodDescriptor(typing.Generic[P, R, AIO_P, AIO_R]):
    """Descriptor that provides both sync and async method variants via .aio() for instance methods"""

    sync_wrapper: Callable[Concatenate[Any, P], R]
    aio_wrapper: Callable[Concatenate[Any, AIO_P], AIO_R]

    def __init__(
        self,
        sync_wrapper: Callable[Concatenate[Any, P], R],
        aio_wrapper: Callable[Concatenate[Any, AIO_P], AIO_R],
    ):
        self.sync_wrapper = sync_wrapper
        self.aio_wrapper = aio_wrapper

    @overload
    def __get__(self, wrapper_instance: None, owner: type) -> typing.Self: ...

    @overload
    def __get__(self, wrapper_instance: T, owner: type) -> MethodWrapper[T, P, R, AIO_P, AIO_R]: ...

    def __get__(self, wrapper_instance, owner) -> MethodWrapper[T, P, R, AIO_P, AIO_R] | typing.Self:
        if wrapper_instance is None:
            # For class access, return self to allow descriptor access
            return self  # type: ignore

        # Create instance with wrapper_instance bound
        return MethodWrapper(wrapper_instance, self.sync_wrapper, self.aio_wrapper)


class WrappedClassMethodDescriptor(typing.Generic[P, R, AIO_P, AIO_R]):
    """Descriptor for classmethods with sync/async variants via .aio()"""

    sync_wrapper: Callable[Concatenate[type, P], R]
    aio_wrapper: Callable[Concatenate[type, AIO_P], AIO_R]

    def __init__(
        self,
        sync_wrapper: Callable[Concatenate[type, P], R],
        aio_wrapper: Callable[Concatenate[type, AIO_P], AIO_R],
    ):
        self.sync_wrapper = sync_wrapper
        self.aio_wrapper = aio_wrapper

    @overload
    def __get__(self, wrapper_instance: None, owner: type) -> ClassOrStaticMethodWrapper[P, R, AIO_P, AIO_R]: ...

    @overload
    def __get__(self, wrapper_instance: typing.Any, owner: type) -> ClassOrStaticMethodWrapper[P, R, AIO_P, AIO_R]: ...

    def __get__(
        self, wrapper_instance: typing.Any | None, owner: type
    ) -> ClassOrStaticMethodWrapper[P, R, AIO_P, AIO_R]:
        return ClassOrStaticMethodWrapper(owner, self.sync_wrapper, self.aio_wrapper)  # type: ignore


class WrappedStaticMethodDescriptor(typing.Generic[P, R, AIO_P, AIO_R]):
    """Descriptor for staticmethods with sync/async variants via .aio()"""

    sync_wrapper: Callable[P, R]
    aio_wrapper: Callable[AIO_P, AIO_R]

    def __init__(
        self,
        sync_wrapper: Callable[P, R],
        aio_wrapper: Callable[AIO_P, AIO_R],
    ):
        self.sync_wrapper = sync_wrapper
        self.aio_wrapper = aio_wrapper

    @overload
    def __get__(self, wrapper_instance: None, owner: type) -> StaticMethodWrapper[P, R, AIO_P, AIO_R]: ...

    @overload
    def __get__(self, wrapper_instance: typing.Any, owner: type) -> StaticMethodWrapper[P, R, AIO_P, AIO_R]: ...

    def __get__(self, wrapper_instance: typing.Any | None, owner: type) -> StaticMethodWrapper[P, R, AIO_P, AIO_R]:
        return StaticMethodWrapper(owner, self.sync_wrapper, self.aio_wrapper)  # type: ignore


def wrapped_method(
    aio_wrapper: Callable[Concatenate[Any, AIO_P], AIO_R],
) -> typing.Callable[[Callable[Concatenate[Any, P], R]], WrappedMethodDescriptor[P, R, AIO_P, AIO_R]]:
    """
    Decorator that creates a descriptor for an instance method.

    Args:
        aio_wrapper: The async wrapper function (takes bound instance + args)

    Returns:
        A decorator that takes the sync wrapper (the method body) and creates a WrappedMethodDescriptor
    """

    def decorator(sync_wrapper: Callable[Concatenate[Any, P], R]) -> WrappedMethodDescriptor[P, R, AIO_P, AIO_R]:
        return WrappedMethodDescriptor(sync_wrapper, aio_wrapper)

    return decorator


def wrapped_classmethod(
    aio_wrapper: Callable[Concatenate[type, AIO_P], AIO_R],
) -> typing.Callable[[Callable[Concatenate[type, P], R]], WrappedClassMethodDescriptor[P, R, AIO_P, AIO_R]]:
    """
    Decorator that creates a descriptor for a classmethod.

    Args:
        aio_wrapper: The async wrapper function (takes bound class + args)

    Returns:
        A decorator that takes the sync wrapper (the method body) and creates a WrappedClassMethodDescriptor
    """

    def decorator(
        sync_wrapper: Callable[Concatenate[type, P], R],
    ) -> WrappedClassMethodDescriptor[P, R, AIO_P, AIO_R]:
        return WrappedClassMethodDescriptor(sync_wrapper, aio_wrapper)

    return decorator


def wrapped_staticmethod(
    aio_wrapper: Callable[AIO_P, AIO_R],
) -> typing.Callable[[Callable[P, R]], WrappedStaticMethodDescriptor[P, R, AIO_P, AIO_R]]:
    """
    Decorator that creates a descriptor for a staticmethod.

    Args:
        aio_wrapper: The async wrapper function (takes args, no bound instance)

    Returns:
        A decorator that takes the sync wrapper (the method body) and creates a WrappedStaticMethodDescriptor
    """

    def decorator(
        sync_wrapper: Callable[P, R],
    ) -> WrappedStaticMethodDescriptor[P, R, AIO_P, AIO_R]:
        return WrappedStaticMethodDescriptor(sync_wrapper, aio_wrapper)

    return decorator


T = typing.TypeVar("T")


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
