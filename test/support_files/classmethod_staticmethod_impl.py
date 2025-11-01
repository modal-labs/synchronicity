"""Test implementation with classmethod and staticmethod."""

import asyncio

from synchronicity import Module

wrapper_module = Module("test_support")


@wrapper_module.wrap_class
class TestClass:
    def __init__(self, value: int):
        self.value = value

    async def instance_method(self) -> int:
        await asyncio.sleep(0.01)
        return self.value

    @classmethod
    async def async_classmethod(cls, multiplier: int) -> int:
        await asyncio.sleep(0.01)
        return 42 * multiplier

    @classmethod
    def sync_classmethod(cls, value: str) -> str:
        return f"sync_{value}"

    @staticmethod
    async def async_staticmethod(x: int, y: int) -> int:
        await asyncio.sleep(0.01)
        return x + y

    @staticmethod
    def sync_staticmethod(text: str) -> str:
        return f"static_{text}"
