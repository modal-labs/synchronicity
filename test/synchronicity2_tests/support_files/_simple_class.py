"""Simple class with async methods, no dependencies on other classes."""

import typing

from synchronicity2 import get_synchronizer

lib = get_synchronizer("simple_class_lib")


@lib.wrap()
class Counter:
    """A simple counter class."""

    count: int

    def __init__(self, start: int = 0):
        self.count = start

    async def increment(self) -> int:
        """Increment and return the new count."""
        self.count += 1
        return self.count

    async def get_multiples(self, n: int) -> typing.AsyncGenerator[int, None]:
        """Generate multiples of the count."""
        for i in range(n):
            yield self.count * i
