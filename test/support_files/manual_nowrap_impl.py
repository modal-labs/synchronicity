"""Support file covering manual-wrapper re-exports."""

from __future__ import annotations

import typing

from synchronicity import MethodSurfaceBase, Module
from synchronicity.descriptor import wrapped_surface_function, wrapped_surface_method

wrapper_module = Module("manual_nowrap")


class _ManualFunctionSurface:
    def __init__(self, sync_impl: typing.Callable[..., typing.Any]):
        self._sync_impl = sync_impl

    def __call__(self, value: int) -> str:
        return self._sync_impl(value)

    async def aio(self, value: int) -> str:
        return f"manual-function-aio:{value}"


@wrapper_module.wrap_function()
@wrapper_module.manual_wrapper()
@wrapped_surface_function(_ManualFunctionSurface)
def manual_function(value: int) -> str:
    return f"manual-function-sync:{value}"


class _ManualMethodSurface(MethodSurfaceBase):
    def __call__(self, value: int) -> str:
        return self._sync_impl(value)

    async def aio(self, value: int) -> str:
        impl_instance = getattr(self._wrapper_instance, "_impl_instance", self._wrapper_instance)
        return f"{impl_instance.prefix}:manual-method-aio:{value}"


@wrapper_module.wrap_class()
class ManualBox:
    def __init__(self, prefix: str):
        self.prefix = prefix

    @wrapper_module.manual_wrapper()
    @wrapped_surface_method(_ManualMethodSurface)
    def manual_method(self, value: int) -> str:
        impl_instance = getattr(self, "_impl_instance", self)
        return f"{impl_instance.prefix}:manual-method-sync:{value}"

    async def auto_method(self, value: int) -> str:
        return f"{self.prefix}:auto-method:{value}"


@wrapper_module.wrap_class()
@wrapper_module.manual_wrapper()
class DirectBox:
    def __init__(self, value: str):
        self.value = value

    def reveal(self) -> str:
        return f"direct:{self.value}"
