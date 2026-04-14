from __future__ import annotations

import typing
from typing import Any, Callable, Concatenate, ParamSpec, TypeVar, assert_type, overload

P = ParamSpec("P")
AIO_P = ParamSpec("AIO_P")
R = TypeVar("R")
AIO_R = TypeVar("AIO_R")


class BoundMethodWithAio(typing.Generic[P, R, AIO_P, AIO_R]):
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
    def __get__(self, wrapper_instance: object, owner: type) -> BoundMethodWithAio[P, R, AIO_P, AIO_R]: ...

    def __get__(self, wrapper_instance, owner):
        if wrapper_instance is None:
            return self
        return BoundMethodWithAio(
            self.sync_wrapper.__get__(wrapper_instance, owner),
            self.aio_wrapper.__get__(wrapper_instance, owner),
        )


def wrapped_method(
    aio_wrapper: Callable[Concatenate[Any, AIO_P], AIO_R],
    sync_wrapper: Callable[Concatenate[Any, P], R],
) -> Callable[[Callable[..., Any]], WrappedMethodDescriptor[P, R, AIO_P, AIO_R]]:
    def decorator(_body: Callable[..., Any]) -> WrappedMethodDescriptor[P, R, AIO_P, AIO_R]:
        return WrappedMethodDescriptor(sync_wrapper, aio_wrapper)

    return decorator


class Example:
    @overload
    def _sync_method(self, value: int) -> int: ...

    @overload
    def _sync_method(self, value: str) -> str: ...

    def _sync_method(self, value: int | str) -> int | str:
        return value

    @overload
    async def _aio_method(self, value: int) -> int: ...

    @overload
    async def _aio_method(self, value: str) -> str: ...

    async def _aio_method(self, value: int | str) -> int | str:
        return value

    @wrapped_method(_aio_method, _sync_method)
    def wrapped_meth(self) -> Any: ...


example = Example()
assert_type(example.wrapped_meth(1), int)
assert_type(example.wrapped_meth("x"), str)

example.wrapped_meth


async def _check_method() -> None:
    async_number = await example.wrapped_meth.aio(1)
    assert_type(async_number, int)
    async_text = await example.wrapped_meth.aio("x")
    assert_type(async_text, str)
