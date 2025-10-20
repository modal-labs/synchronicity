"""Module A for multifile integration testing."""
from synchronicity2.synchronizer import get_synchronizer

from ._b import B

s = get_synchronizer("s")


@s.wrap()
class A:
    """A test class."""

    def __init__(self, value: int = 42):
        self.value = value

    async def get_value(self) -> int:
        return self.value


@s.wrap()
async def get_b() -> B:
    """Create and return a B instance."""
    return B()
