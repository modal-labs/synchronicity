"""Integration tests for event_loop_check_impl.py support file.

Tests that .aio() methods execute in the synchronizer's event loop.
"""

import asyncio


def test_event_loop_execution(generated_wrappers):
    """Test that .aio() methods run in the synchronizer's event loop."""

    import event_loop_check

    # Test 1: Function .aio()
    async def test_function_aio():
        result = await event_loop_check.async_function.aio(5)
        return result

    result1 = asyncio.run(test_function_aio())
    assert result1 == 10, f"Expected 10, got {result1}"
    print(f"✓ Function .aio() runs in synchronizer event loop: {result1}")

    # Test 2: Generator function .aio()
    async def test_generator_aio():
        results = []
        async for val in event_loop_check.async_generator.aio(3):
            results.append(val)
        return results

    result2 = asyncio.run(test_generator_aio())
    assert result2 == [0, 1, 2], f"Expected [0, 1, 2], got {result2}"
    print(f"✓ Generator function .aio() runs in synchronizer event loop: {result2}")

    # Test 3: Method .aio()
    checker = event_loop_check.EventLoopChecker(10)

    async def test_method_aio():
        result = await checker.async_method.aio()
        return result

    result3 = asyncio.run(test_method_aio())
    assert result3 == 20, f"Expected 20, got {result3}"
    print(f"✓ Method .aio() runs in synchronizer event loop: {result3}")

    # Test 4: Generator method .aio()
    async def test_generator_method_aio():
        results = []
        async for val in checker.async_generator_method.aio(3):
            results.append(val)
        return results

    result4 = asyncio.run(test_generator_method_aio())
    assert result4 == [0, 10, 20], f"Expected [0, 10, 20], got {result4}"
    print(f"✓ Generator method .aio() runs in synchronizer event loop: {result4}")
