import typing
from typing import Any, Callable, Concatenate, ParamSpec, TypeVar, overload

T = TypeVar("T")
P = ParamSpec("P")
R = TypeVar("R")
Surface_co = TypeVar("Surface_co", covariant=True)


class _BoundInstanceMethodDescriptorSurface(typing.Protocol[Surface_co]):
    @overload
    def __get__(self, wrapper_instance: None, owner: type) -> typing.Self: ...

    @overload
    def __get__(self, wrapper_instance: typing.Any, owner: type) -> Surface_co: ...


class _BoundOnAccessDescriptorSurface(typing.Protocol[Surface_co]):
    def __get__(self, wrapper_instance: typing.Any | None, owner: type) -> Surface_co: ...


class SurfaceMethodDescriptor(typing.Generic[Surface_co]):
    """Descriptor that materializes a generated surface object for instance methods."""

    sync_wrapper: Callable[..., typing.Any]
    surface_factory: Callable[..., Surface_co]

    def __init__(self, sync_wrapper: Callable[..., typing.Any], surface_factory: Callable[..., Surface_co]):
        self.sync_wrapper = sync_wrapper
        self.surface_factory = surface_factory

    @overload
    def __get__(self, wrapper_instance: None, owner: type) -> typing.Self: ...

    @overload
    def __get__(self, wrapper_instance: typing.Any, owner: type) -> Surface_co: ...

    def __get__(self, wrapper_instance, owner):
        if wrapper_instance is None:
            return self
        return self.surface_factory(
            sync_impl=self.sync_wrapper.__get__(wrapper_instance, owner),
            wrapper_instance=wrapper_instance,
            wrapper_class=owner,
            _from_impl=owner._from_impl,
        )


class SurfaceOnAccessDescriptor(typing.Generic[Surface_co]):
    """Descriptor that materializes a generated surface object on each access."""

    sync_wrapper: Callable[..., typing.Any]
    surface_factory: Callable[..., Surface_co]

    def __init__(self, sync_wrapper: Callable[..., typing.Any], surface_factory: Callable[..., Surface_co]):
        self.sync_wrapper = sync_wrapper
        self.surface_factory = surface_factory

    def __get__(self, wrapper_instance: typing.Any | None, owner: type) -> Surface_co:
        return self.surface_factory(
            sync_impl=self.sync_wrapper.__get__(wrapper_instance, owner),
            wrapper_instance=wrapper_instance,
            wrapper_class=owner,
            _from_impl=owner._from_impl,
        )


def wrapped_surface_function(
    surface_factory: Callable[..., Surface_co],
) -> typing.Callable[[Callable[P, R]], Surface_co]:
    def decorator(
        sync_wrapper: Callable[P, R],
    ) -> Surface_co:
        return surface_factory(sync_impl=sync_wrapper)

    return decorator


def wrapped_overloaded_function(
    surface_factory: Callable[..., Surface_co],
) -> typing.Callable[[Callable[P, R]], Surface_co]:
    return wrapped_surface_function(surface_factory)


def wrapped_surface_method(
    surface_factory: Callable[..., Surface_co],
) -> typing.Callable[[Callable[Concatenate[Any, P], R]], _BoundInstanceMethodDescriptorSurface[Surface_co]]:
    def decorator(
        sync_wrapper: Callable[Concatenate[Any, P], R],
    ) -> _BoundInstanceMethodDescriptorSurface[Surface_co]:
        return SurfaceMethodDescriptor(sync_wrapper, surface_factory)

    return decorator


def wrapped_overloaded_method(
    surface_factory: Callable[..., Surface_co],
) -> typing.Callable[[Callable[Concatenate[Any, P], R]], _BoundInstanceMethodDescriptorSurface[Surface_co]]:
    return wrapped_surface_method(surface_factory)


def wrapped_surface_classmethod(
    surface_factory: Callable[..., Surface_co],
) -> typing.Callable[
    [
        Callable[Concatenate[type[T], P], R],
    ],
    _BoundOnAccessDescriptorSurface[Surface_co],
]:
    def decorator(
        sync_wrapper: Callable[Concatenate[type[T], P], R],
    ) -> _BoundOnAccessDescriptorSurface[Surface_co]:
        return SurfaceOnAccessDescriptor(sync_wrapper, surface_factory)

    return decorator


def wrapped_overloaded_classmethod(
    surface_factory: Callable[..., Surface_co],
) -> typing.Callable[
    [
        Callable[Concatenate[type[T], P], R],
    ],
    _BoundOnAccessDescriptorSurface[Surface_co],
]:
    return wrapped_surface_classmethod(surface_factory)


def wrapped_surface_staticmethod(
    surface_factory: Callable[..., Surface_co],
) -> typing.Callable[[Callable[P, R]], _BoundOnAccessDescriptorSurface[Surface_co]]:
    def decorator(
        sync_wrapper: Callable[P, R],
    ) -> _BoundOnAccessDescriptorSurface[Surface_co]:
        return SurfaceOnAccessDescriptor(sync_wrapper, surface_factory)

    return decorator


def wrapped_overloaded_staticmethod(
    surface_factory: Callable[..., Surface_co],
) -> typing.Callable[[Callable[P, R]], _BoundOnAccessDescriptorSurface[Surface_co]]:
    return wrapped_surface_staticmethod(surface_factory)
