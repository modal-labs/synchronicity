"""Integration tests for overload-support wrapper generation."""

from __future__ import annotations

import asyncio
from importlib.util import find_spec
from pathlib import Path

from test.integration.test_utils import check_pyright


def test_runtime():
    import overloads

    assert overloads.duplicate(4) == 8
    assert overloads.duplicate("ab") == "abab"

    record = overloads.Record(6)
    assert record.value == 6

    resolver = overloads.Resolver(5)
    assert resolver.resolve(2) == 7
    assert resolver.resolve("name") == "name:5"

    async def check_async() -> None:
        assert await overloads.duplicate.aio(4) == 8
        assert await overloads.duplicate.aio("ab") == "abab"

        assert await resolver.resolve.aio(2) == 7
        assert await resolver.resolve.aio("name") == "name:5"

    asyncio.run(check_async())


def test_generated_wrapper_contains_overloads():
    import overloads

    source = Path(overloads.__file__).read_text()

    assert "class _duplicate_FunctionSurface(typing.Protocol):" in source
    assert "def __call__(self, value: int) -> int: ..." in source
    assert "def __call__(self, value: str) -> str: ..." in source
    assert "def aio(self, value: int) -> typing.Coroutine[typing.Any, typing.Any, int]: ..." in source
    assert "def aio(self, value: str) -> typing.Coroutine[typing.Any, typing.Any, str]: ..." in source
    assert "@wrapped_overloaded_function(__duplicate_aio, surface_type=_duplicate_FunctionSurface)" in source
    assert "class _Resolver_resolve_MethodSurface(typing.Protocol):" in source
    assert "def __call__(self, value: int) -> int: ..." in source
    assert "def __call__(self, value: str) -> str: ..." in source
    assert "def aio(self, value: int) -> typing.Coroutine[typing.Any, typing.Any, int]: ..." in source
    assert "def aio(self, value: str) -> typing.Coroutine[typing.Any, typing.Any, str]: ..." in source
    assert "@wrapped_overloaded_method(__resolve_aio, surface_type=_Resolver_resolve_MethodSurface)" in source


def test_pyright_implementation():
    import overloads_impl

    check_pyright([Path(overloads_impl.__file__)])


def test_pyright_wrapper():
    import overloads

    check_pyright([Path(overloads.__file__)])


def test_pyright_usage():
    spec = find_spec("overloads_typecheck")
    assert spec and spec.origin
    check_pyright([Path(spec.origin)])
