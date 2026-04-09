"""Parse-only tests: live functions → :class:`~synchronicity.codegen.ir.ModuleLevelFunctionIR`.

No emission; integration tests cover parse+emit end-to-end.
"""

from __future__ import annotations

import typing
from typing import Awaitable, Coroutine

from synchronicity.codegen.parse import parse_module_level_function_ir
from synchronicity.codegen.transformer_ir import AwaitableTypeIR, CoroutineTypeIR


def test_parse_sync_function_no_async_wrapper():
    def add(a: int, b: int) -> int:
        return a + b

    ir = parse_module_level_function_ir(add, "m", {}, globals_dict=globals())
    assert ir.needs_async_wrapper is False
    assert ir.is_async_gen is False


def test_parse_sync_function_returning_coroutine_needs_async_wrapper():
    def create_c(x: int) -> Coroutine[typing.Any, typing.Any, str]: ...

    ir = parse_module_level_function_ir(create_c, "m", {}, globals_dict=globals())
    assert ir.needs_async_wrapper is True
    assert isinstance(ir.return_transformer_ir, CoroutineTypeIR)


def test_parse_sync_function_returning_awaitable_needs_async_wrapper():
    def create_a(x: int) -> Awaitable[str]: ...

    ir = parse_module_level_function_ir(create_a, "m", {}, globals_dict=globals())
    assert ir.needs_async_wrapper is True
    assert isinstance(ir.return_transformer_ir, AwaitableTypeIR)
