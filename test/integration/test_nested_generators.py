"""Integration tests for nested_generators_impl.py support file.

Tests that nested async generators in tuples work correctly end-to-end.
"""

import asyncio


def test_nested_async_generators_in_tuple(generated_wrappers):
    """Test that nested async generators in tuples work end-to-end.

    This tests the case where a function returns a tuple containing async generators,
    verifying that both sync and async interfaces work correctly.
    """
    # Test 1: Sync interface returns sync generators (wrapped)
    import nested_generators

    # Test sync interface:
    str_gen_sync, int_gen_sync = nested_generators.nested_async_generator(3)

    str_results = []
    for s in str_gen_sync:
        str_results.append(s)

    int_results = []
    for i in int_gen_sync:
        int_results.append(i)

    assert str_results == [
        "hello",
        "hello",
        "hello",
    ], f"Expected ['hello', 'hello', 'hello'], got {str_results}"
    assert int_results == [0, 1, 2], f"Expected [0, 1, 2], got {int_results}"
    print(f"✓ Sync interface: str_gen yielded {str_results}")
    print(f"✓ Sync interface: int_gen yielded {int_results}")

    # Test 2: Async interface - iterate over both generators
    async def test_async():
        str_gen, int_gen = await nested_generators.nested_async_generator.aio(2)

        str_results = []
        async for s in str_gen:
            str_results.append(s)

        int_results = []
        async for i in int_gen:
            int_results.append(i)

        assert str_results == ["hello", "hello"], f"Expected ['hello', 'hello'], got {str_results}"
        assert int_results == [0, 1], f"Expected [0, 1], got {int_results}"
        return str_results, int_results

    str_results, int_results = asyncio.run(test_async())
    print(f"✓ Async interface: str_gen yielded {str_results}")
    print(f"✓ Async interface: int_gen yielded {int_results}")

    # Test 3: Verify generators in tuple are independent
    async def test_independence():
        str_gen1, int_gen1 = await nested_generators.nested_async_generator.aio(1)
        # Consume only str_gen1
        async for _ in str_gen1:
            pass
        # int_gen1 should still work independently
        int_results = []
        async for i in int_gen1:
            int_results.append(i)
        return int_results

    int_results = asyncio.run(test_independence())
    assert int_results == [0], f"Expected [0], got {int_results}"
    print("✓ Generators in tuple are independent")
