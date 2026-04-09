"""Integration tests for two_way_generator_impl.py support file."""

import asyncio
import pytest
import time
from pathlib import Path

from test.integration.test_utils import check_pyright


def test_runtime():
    import two_way_generator

    gen = two_way_generator.echo_generator()
    first = gen.send(None)
    assert first == "Ready"
    assert gen.send("Hello") == "Echo: Hello"
    assert gen.send("World") == "Echo: World"
    assert gen.send(None) == "Got None"
    gen.close()

    async def test_echo_async():
        gen = two_way_generator.echo_generator.aio()
        assert await gen.asend(None) == "Ready"
        assert await gen.asend("Async") == "Echo: Async"
        await gen.aclose()

    asyncio.run(test_echo_async())

    gen = two_way_generator.accumulator_generator()
    assert gen.send(None) == 0
    assert gen.send(5) == 5
    assert gen.send(10) == 15
    assert gen.send(None) == 15
    gen.close()

    gen = two_way_generator.multiplier_generator(3)
    assert gen.send(None) == 0
    assert gen.send(5) == 15
    assert gen.send(7) == 21
    assert gen.send(None) == 0
    gen.close()


def test_runtime_aclose_forwarding():
    import two_way_generator
    import two_way_generator_impl

    async def test_async_aclose():
        gen = two_way_generator.generator_with_cleanup.aio()
        assert await gen.asend(None) == "first"
        assert await gen.asend(None) == "second"
        assert len(two_way_generator_impl.cleanup_tracker) == 0
        start_time = time.time()
        await gen.aclose()
        elapsed_time = time.time() - start_time
        assert elapsed_time >= 1.0
        assert len(two_way_generator_impl.cleanup_tracker) == 1
        assert two_way_generator_impl.cleanup_tracker[0] == "cleanup_called"

    asyncio.run(test_async_aclose())

    gen = two_way_generator.generator_with_cleanup()
    assert gen.send(None) == "first"
    assert gen.send(None) == "second"
    assert len(two_way_generator_impl.cleanup_tracker) == 0
    start_time = time.time()
    gen.close()
    elapsed_time = time.time() - start_time
    assert elapsed_time >= 1.0
    assert len(two_way_generator_impl.cleanup_tracker) == 1
    assert two_way_generator_impl.cleanup_tracker[0] == "cleanup_called"


def test_pyright_implementation():
    import two_way_generator_impl

    check_pyright([Path(two_way_generator_impl.__file__)])


@pytest.mark.xfail(
    strict=True,
    reason="Generated two-way generator module triggers reportRedeclaration for per-function helpers",
)
def test_pyright_wrapper():
    import two_way_generator

    check_pyright([Path(two_way_generator.__file__)])


def test_pyright_usage():
    from importlib.util import find_spec

    spec = find_spec("two_way_generator_typecheck")
    assert spec and spec.origin
    check_pyright([Path(spec.origin)])
