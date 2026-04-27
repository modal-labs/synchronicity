"""Consumer typing checks for async staticmethods with method-local type variables."""

from typing import assert_type

import staticmethod_method_local_typevar


def _sync_usage() -> None:
    assert_type(staticmethod_method_local_typevar.EchoBox.echo(3), int)
    assert_type(staticmethod_method_local_typevar.EchoBox.echo("hi"), str)


async def _async_usage() -> None:
    assert_type(await staticmethod_method_local_typevar.EchoBox.echo.aio(4), int)
    assert_type(await staticmethod_method_local_typevar.EchoBox.echo.aio("bye"), str)
