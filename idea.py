import typing
from typing import Any, Callable, Concatenate, overload

T = typing.TypeVar("T")
P = typing.ParamSpec("P")
R = typing.TypeVar("R")
AIO_P = typing.ParamSpec("AIO_P")
AIO_R = typing.TypeVar("AIO_R")


class MethodWrapper(typing.Generic[T, P, R, AIO_P, AIO_R]):
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
            return self

        # Create instance with wrapper_instance bound
        return MethodWrapper(wrapper_instance, self.sync_wrapper, self.aio_wrapper)


def aio_enriched_method(
    aio_wrapper: Callable[Concatenate[Any, AIO_P], AIO_R],
) -> typing.Callable[[Callable[Concatenate[Any, P], R]], WrappedMethodDescriptor[P, R, AIO_P, AIO_R]]:
    def decorator(sync_wrapper: Callable[Concatenate[Any, P], R]) -> WrappedMethodDescriptor[P, R, AIO_P, AIO_R]:
        return WrappedMethodDescriptor(sync_wrapper, aio_wrapper)

    return decorator


async def some_method_aio(self: "SomeClass", x: int) -> float: ...


class SomeClass:
    @aio_enriched_method(some_method_aio)
    def some_method(self, x: int) -> float: ...


sc = SomeClass()

sc.some_method
res = sc.some_method.aio(10)
