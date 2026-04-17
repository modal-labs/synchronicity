import typing
from typing import Any, Callable, Concatenate, ParamSpec, TypeVar, overload

T = TypeVar("T")
P = ParamSpec("P")
R = TypeVar("R")
Surface_co = TypeVar("Surface_co", covariant=True)


class MethodSurfaceBase:
    """Shared runtime base for generated and custom method-surface classes."""

    _sync_impl: Callable[..., typing.Any]
    _wrapper_instance: typing.Any
    _wrapper_class: type
    _surface_from_impl: Callable[[typing.Any], typing.Any]

    def __init__(
        self,
        sync_impl: Callable[..., typing.Any],
        wrapper_instance: typing.Any,
        wrapper_class: type,
        _from_impl: Callable[[typing.Any], typing.Any],
    ):
        self._sync_impl = sync_impl
        self._wrapper_instance = wrapper_instance
        self._wrapper_class = wrapper_class
        self._surface_from_impl = _from_impl

    def _from_impl(self, impl_instance: typing.Any) -> typing.Any:
        return self._surface_from_impl(impl_instance)


class _BoundInstanceMethodDescriptorSurface(typing.Protocol[Surface_co]):
    @overload
    def __get__(self, wrapper_instance: None, owner: type) -> typing.Self: ...

    @overload
    def __get__(self, wrapper_instance: typing.Any, owner: type) -> Surface_co: ...


class _BoundOnAccessDescriptorSurface(typing.Protocol[Surface_co]):
    def __get__(self, wrapper_instance: typing.Any | None, owner: type) -> Surface_co: ...


class SurfaceMethodDescriptor(typing.Generic[Surface_co]):
    """Descriptor that materializes a generated surface object for instance methods."""

    _synchronicity_raw_class_dict = False
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

    _synchronicity_raw_class_dict = True
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


def wrapped_surface_method(
    surface_factory: Callable[..., Surface_co],
) -> typing.Callable[[Callable[Concatenate[Any, P], R]], _BoundInstanceMethodDescriptorSurface[Surface_co]]:
    def decorator(
        sync_wrapper: Callable[Concatenate[Any, P], R],
    ) -> _BoundInstanceMethodDescriptorSurface[Surface_co]:
        return SurfaceMethodDescriptor(sync_wrapper, surface_factory)

    return decorator


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


def wrapped_surface_staticmethod(
    surface_factory: Callable[..., Surface_co],
) -> typing.Callable[[Callable[P, R]], _BoundOnAccessDescriptorSurface[Surface_co]]:
    def decorator(
        sync_wrapper: Callable[P, R],
    ) -> _BoundOnAccessDescriptorSurface[Surface_co]:
        return SurfaceOnAccessDescriptor(sync_wrapper, surface_factory)

    return decorator
