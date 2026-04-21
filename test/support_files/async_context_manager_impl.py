import threading
import typing
from contextlib import asynccontextmanager

import synchronicity2

mod = synchronicity2.Module("async_context_manager")


@mod.wrap_class()
class AsyncResource:
    """A class implementing the async context manager protocol directly."""

    name: str
    state: str

    def __init__(self, name: str):
        self.name = name
        self.state = "init"

    async def __aenter__(self) -> typing.Self:
        assert threading.current_thread().ident != threading.main_thread().ident
        self.state = "entered"
        return self

    async def __aexit__(
        self,
        exc_type: typing.Optional[type[BaseException]],
        exc_val: typing.Optional[BaseException],
        exc_tb: typing.Any,
    ) -> None:
        assert threading.current_thread().ident != threading.main_thread().ident
        self.state = "exited"


@mod.wrap_class()
class Connection:
    """A wrapped type yielded from context managers to test impl→wrapper translation."""

    value: int

    def __init__(self, value: int):
        self.value = value


@mod.wrap_function()
@asynccontextmanager
async def managed_value() -> typing.AsyncGenerator[Connection, None]:
    """A module-level context manager created via @asynccontextmanager."""
    assert threading.current_thread().ident != threading.main_thread().ident
    yield Connection(42)


@mod.wrap_class()
class ServiceWithContextMethod:
    """A class with a method that returns a context manager."""

    @asynccontextmanager
    async def connect(self) -> typing.AsyncGenerator[Connection, None]:
        assert threading.current_thread().ident != threading.main_thread().ident
        yield Connection(99)
