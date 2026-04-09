"""Integration tests for simple_class_impl.py support file."""

import asyncio
from pathlib import Path

from test.integration.test_utils import check_pyright


def test_runtime():
    import simple_class

    counter = simple_class.Counter(10)
    assert counter.count == 10

    result = counter.increment()
    assert result == 11
    assert counter.count == 11

    multiples = list(counter.get_multiples(3))
    assert multiples == [0, 11, 22]

    assert counter.sync_method() == 11
    assert not hasattr(counter.sync_method, "aio")

    counter2 = simple_class.Counter(5)

    async def test_async_method():
        result = await counter2.increment.aio()
        return result

    assert asyncio.run(test_async_method()) == 6

    async def test_async_generator_method():
        results = []
        async for val in counter2.get_multiples.aio(3):
            results.append(val)
        return results

    assert asyncio.run(test_async_generator_method()) == [0, 6, 12]


def test_pyright_implementation():
    import simple_class_impl

    check_pyright([Path(simple_class_impl.__file__)])


def test_pyright_wrapper():
    import simple_class

    check_pyright([Path(simple_class.__file__)])


def test_pyright_usage():
    from importlib.util import find_spec

    spec = find_spec("simple_class_typecheck")
    assert spec and spec.origin
    check_pyright([Path(spec.origin)])
