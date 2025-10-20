"""Module B for multifile integration testing."""
import typing

from synchronicity2.synchronizer import get_synchronizer

if typing.TYPE_CHECKING:
    from ._a import A

s = get_synchronizer("s")


@s.wrap()
class B:
    """B test class."""

    def __init__(self, name: str = "test"):
        self.name = name

    async def get_name(self) -> str:
        return self.name


@s.wrap()
async def get_a() -> "A":
    """Create and return an A instance."""
    from ._a import A

    return A()
