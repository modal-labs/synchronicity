"""Integration tests for simple_class_impl.py support file.

Tests execution and type checking of generated code for simple async classes.
"""

import asyncio
from pathlib import Path

from synchronicity.codegen.compile import compile_modules
from synchronicity.codegen.writer import write_modules
from test.integration.test_utils import check_pyright


def test_generated_code_execution_class(generated_wrappers):
    """Test that generated class wrappers work correctly."""
    # Test the wrapper class
    counter = generated_wrappers.simple_class.Counter(10)
    assert counter.count == 10, f"Expected count=10, got {counter.count}"

    # Test method call
    result = counter.increment()
    assert result == 11, f"Expected 11, got {result}"
    assert counter.count == 11, f"Expected count=11, got {counter.count}"

    # Test generator method
    multiples = list(counter.get_multiples(3))
    assert multiples == [0, 11, 22], f"Expected [0, 11, 22], got {multiples}"

    print("✓ Generated class execution test passed")


def test_method_wrapper_aio_execution(generated_wrappers):
    """Test that generated method wrappers execute correctly with .aio()."""
    # Test method wrapper .aio() calls run properly
    counter = generated_wrappers.simple_class.Counter(5)

    async def test_async_method():
        result = await counter.increment.aio()
        return result

    result = asyncio.run(test_async_method())
    assert result == 6, f"Expected 6, got {result}"
    print(f"✓ Method wrapper .aio() execution: async method returned {result}")

    async def test_async_generator_method():
        results = []
        async for val in counter.get_multiples.aio(3):
            results.append(val)
        return results

    result = asyncio.run(test_async_generator_method())
    assert result == [0, 6, 12], f"Expected [0, 6, 12], got {result}"
    print(f"✓ Method wrapper .aio() execution: async generator returned {result}")


def test_pyright_simple_class(tmpdir):
    """Test that simple class generation passes pyright."""
    import simple_class_impl

    # Generate wrapper code
    modules = compile_modules([simple_class_impl.wrapper_module], "s")
    module_paths = list(write_modules(Path(tmpdir), modules))

    # Verify type correctness with pyright
    check_pyright(module_paths, str(tmpdir))
