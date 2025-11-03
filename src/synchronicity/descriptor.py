import typing
from typing import Any, Callable, Concatenate, ParamSpec, TypeVar, overload

T = TypeVar("T")
P = ParamSpec("P")
R = TypeVar("R")
AIO_P = ParamSpec("AIO_P")
AIO_R = TypeVar("AIO_R")


class FunctionWithAio(typing.Generic[P, R, AIO_P, AIO_R]):
    """Function wrapper that provides both sync and async function variants via .aio(

    Note that .aio here is not itself a coroutine function, but usually delegates to one
    and returns the resulting Coroutine. This allows it to agnostically return async
    generators or context managers as well as other awaitables.
    """

    sync_wrapper: Callable[P, R]
    aio_wrapper: Callable[AIO_P, AIO_R]

    def __init__(
        self,
        sync_wrapper: Callable[P, R],
        aio_wrapper: Callable[AIO_P, AIO_R],
    ):
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
        # capture signature without first argument (`self`)
        sync_wrapper: Callable[Concatenate[Any, P], R],
        aio_wrapper: Callable[Concatenate[Any, AIO_P], AIO_R],
    ):
        self.sync_wrapper = sync_wrapper
        self.aio_wrapper = aio_wrapper

    @overload
    def __get__(self, wrapper_instance: None, owner: type) -> typing.Self: ...

    @overload
    def __get__(self, wrapper_instance: typing.Any, owner: type) -> FunctionWithAio[P, R, AIO_P, AIO_R]: ...

    def __get__(self, wrapper_instance, owner):
        if wrapper_instance is None:
            # For class access, return self to allow descriptor access
            return self

        # Create instance with wrapper_instance bound
        return FunctionWithAio(
            self.sync_wrapper.__get__(wrapper_instance, owner), self.aio_wrapper.__get__(wrapper_instance, owner)
        )


class WrappedStaticMethodDescriptor(typing.Generic[P, R, AIO_P, AIO_R]):
    """Descriptor for staticmethods with sync/async variants via .aio()"""

    sync_wrapper: staticmethod
    aio_wrapper: staticmethod

    def __init__(
        self,
        sync_wrapper: Callable[P, R],
        aio_wrapper: Callable[AIO_P, AIO_R],
    ):
        assert isinstance(sync_wrapper, staticmethod)
        self.sync_wrapper = sync_wrapper
        assert isinstance(aio_wrapper, staticmethod)
        self.aio_wrapper = aio_wrapper

    def __get__(self, wrapper_instance: typing.Any | None, owner: type) -> FunctionWithAio[P, R, AIO_P, AIO_R]:
        return FunctionWithAio(
            self.sync_wrapper.__get__(wrapper_instance, owner), self.aio_wrapper.__get__(wrapper_instance, owner)
        )


class WrappedClassMethodDescriptor(typing.Generic[P, R, AIO_P, AIO_R]):
    """Descriptor for classmethods with sync/async variants via .aio()"""

    sync_wrapper: classmethod
    aio_wrapper: classmethod

    def __init__(
        self,
        # capture the signature without the leading `cls` arg
        sync_wrapper: Callable[Concatenate[Any, P], R],
        aio_wrapper: Callable[Concatenate[Any, AIO_P], AIO_R],
    ):
        assert isinstance(sync_wrapper, classmethod)
        self.sync_wrapper = sync_wrapper
        assert isinstance(aio_wrapper, classmethod)
        self.aio_wrapper = aio_wrapper

    def __get__(self, wrapper_instance: typing.Any | None, owner: type) -> FunctionWithAio[P, R, AIO_P, AIO_R]:
        return FunctionWithAio(
            self.sync_wrapper.__get__(wrapper_instance, owner), self.aio_wrapper.__get__(wrapper_instance, owner)
        )


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
    aio_wrapper: Callable[Concatenate[type[T], AIO_P], AIO_R],
) -> typing.Callable[
    [
        Callable[Concatenate[type[T], P], R],
    ],
    WrappedClassMethodDescriptor[P, R, AIO_P, AIO_R],
]:
    """
    Decorator that creates a descriptor for a classmethod.

    Args:
        aio_wrapper: The async wrapper function (takes bound class + args) or a @classmethod descriptor

    Returns:
        A decorator that takes the sync wrapper (the method body or a @classmethod descriptor)
        and creates a WrappedClassMethodDescriptor
    """

    def decorator(
        sync_wrapper: Callable[Concatenate[type[T], P], R],
    ) -> WrappedClassMethodDescriptor[P, R, AIO_P, AIO_R]:
        # Handle both raw functions and @classmethod-wrapped functions
        return WrappedClassMethodDescriptor(sync_wrapper, aio_wrapper)

    return decorator


def wrapped_staticmethod(
    aio_wrapper: Callable[AIO_P, AIO_R],
) -> typing.Callable[[Callable[P, R]], WrappedStaticMethodDescriptor[P, R, AIO_P, AIO_R]]:
    """
    Decorator that creates a descriptor for a staticmethod.

    Args:
        aio_wrapper: The async wrapper function (takes args, no bound instance) or a @staticmethod descriptor

    Returns:
        A decorator that takes the sync wrapper (the method body or a @staticmethod descriptor)
        and creates a WrappedStaticMethodDescriptor
    """

    def decorator(
        sync_wrapper: Callable[P, R],
    ) -> WrappedStaticMethodDescriptor[P, R, AIO_P, AIO_R]:
        # Handle both raw functions and @staticmethod-wrapped functions
        return WrappedStaticMethodDescriptor(sync_wrapper, aio_wrapper)

    return decorator


def wrapped_function(
    aio_wrapper: Callable[AIO_P, AIO_R],
) -> typing.Callable[[Callable[P, R]], FunctionWithAio[P, R, AIO_P, AIO_R]]:
    """
    Decorator that creates a descriptor for a function.

    Args:
        aio_wrapper: The async wrapper function (takes args, no bound instance)

    Returns:
        A decorator that takes the sync wrapper (the function body) and creates a FunctionWrapper
    """

    def decorator(
        sync_wrapper: Callable[P, R],
    ) -> FunctionWithAio[P, R, AIO_P, AIO_R]:
        return FunctionWithAio(sync_wrapper, aio_wrapper)

    return decorator
