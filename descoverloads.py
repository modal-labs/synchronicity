from __future__ import annotations

import typing
from typing import Any, Callable, assert_type, overload

Surface = typing.TypeVar("Surface", covariant=True)
T_co = typing.TypeVar("T_co", covariant=True)
T = typing.TypeVar("T")


class BoundMethodWithAio:
    def __init__(self, sync_wrapper: Callable[..., Any], aio_wrapper: Callable[..., Any]):
        self.sync_wrapper = sync_wrapper
        self.aio_wrapper = aio_wrapper

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.sync_wrapper(*args, **kwargs)

    def aio(self, *args: Any, **kwargs: Any) -> Any:
        return self.aio_wrapper(*args, **kwargs)


class WrappedMethodDescriptor:
    def __init__(self, sync_wrapper: Callable[..., Any], aio_wrapper: Callable[..., Any]):
        self.sync_wrapper = sync_wrapper
        self.aio_wrapper = aio_wrapper

    def __get__(self, wrapper_instance, owner):
        if wrapper_instance is None:
            return self
        return BoundMethodWithAio(
            self.sync_wrapper.__get__(wrapper_instance, owner),
            self.aio_wrapper.__get__(wrapper_instance, owner),
        )


class _MethodDescriptorSurface(typing.Protocol[Surface]):
    @overload
    def __get__(self, wrapper_instance: None, owner: type) -> typing.Self: ...

    @overload
    def __get__(self, wrapper_instance: object, owner: type) -> Surface: ...


def wrapped_method(
    aio_wrapper: Callable[..., Any],
    *,
    surface_type: type[Surface],
) -> Callable[[Callable[..., Any]], _MethodDescriptorSurface[Surface]]:
    def decorator(sync_wrapper: Callable[..., Any]) -> _MethodDescriptorSurface[Surface]:
        _ = surface_type
        return typing.cast(_MethodDescriptorSurface[Surface], WrappedMethodDescriptor(sync_wrapper, aio_wrapper))

    return decorator


class AdvancedMethodBoundSurface(typing.Protocol[T_co]):
    @overload
    def __call__(self, value: int) -> tuple[T_co, int]: ...

    @overload
    def __call__(self, value: str) -> tuple[T_co, str]: ...

    @overload
    def aio(self, value: int) -> typing.Coroutine[Any, Any, tuple[T_co, int]]: ...

    @overload
    def aio(self, value: str) -> typing.Coroutine[Any, Any, tuple[T_co, str]]: ...


class SelfMethodBoundSurface(typing.Protocol[T_co]):
    def __call__(self) -> T_co: ...

    def aio(self) -> typing.Coroutine[Any, Any, T_co]: ...


class AdvancedExample(typing.Generic[T]):
    def __init__(self, value: T):
        self.value = value

    def _sync_method(self, value: int | str) -> tuple[T, int | str]:
        return (self.value, value)

    async def _aio_method(self, value: int | str) -> tuple[T, int | str]:
        return (self.value, value)

    @wrapped_method(_aio_method, surface_type=AdvancedMethodBoundSurface[T])
    def wrapped_meth(self, value: int | str) -> tuple[T, int | str]:
        return self._sync_method(value)

    def _sync_self(self) -> typing.Self:
        return self

    async def _aio_self(self) -> typing.Self:
        return self

    @wrapped_method(_aio_self, surface_type=SelfMethodBoundSurface[typing.Self])
    def return_self(self) -> typing.Self:
        return self


advanced_int: AdvancedExample[int] = AdvancedExample(1)
advanced_str: AdvancedExample[str] = AdvancedExample("value")
assert_type(advanced_int.wrapped_meth(5), tuple[int, int])
assert_type(advanced_int.wrapped_meth("x"), tuple[int, str])
assert_type(advanced_str.wrapped_meth(5), tuple[str, int])
assert_type(advanced_str.wrapped_meth("x"), tuple[str, str])
assert_type(advanced_int.return_self(), AdvancedExample[int])
assert_type(advanced_str.return_self(), AdvancedExample[str])


async def _check_method() -> None:
    async_number = await advanced_int.wrapped_meth.aio(1)
    assert_type(async_number, tuple[int, int])
    async_text = await advanced_int.wrapped_meth.aio("x")
    assert_type(async_text, tuple[int, str])
    async_number_on_str = await advanced_str.wrapped_meth.aio(1)
    assert_type(async_number_on_str, tuple[str, int])
    async_text_on_str = await advanced_str.wrapped_meth.aio("x")
    assert_type(async_text_on_str, tuple[str, str])
    async_self_int = await advanced_int.return_self.aio()
    assert_type(async_self_int, AdvancedExample[int])
    async_self_str = await advanced_str.return_self.aio()
    assert_type(async_self_str, AdvancedExample[str])
