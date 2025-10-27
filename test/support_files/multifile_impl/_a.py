"""Module A for multifile integration testing."""

from synchronicity import Module

from ._b import B

wrapper_module = Module("multifile.a")


@wrapper_module.wrap_class
class A:
    """A test class."""

    def __init__(self, value: int = 42):
        self.value = value

    async def get_value(self) -> int:
        return self.value


@wrapper_module.wrap_function
async def get_b() -> B:
    """Create and return a B instance."""
    return B()
