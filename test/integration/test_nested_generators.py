"""Integration tests for nested_generators_impl.py support file.

Tests that nested async generators in tuples work correctly end-to-end.
"""

import asyncio


def test_nested_async_generators_in_tuple(generated_wrappers):
    """Test that nested async generators in tuples work end-to-end.

    This tests the case where a function returns a tuple containing async generators,
    verifying that both sync and async interfaces work correctly.
    """
    # Verify helper functions are generated for nested generators
    generated_code = generated_wrappers.generated_code["generated.nested_generators"]
    assert "@staticmethod" in generated_code
    assert "async def _wrap_async_gen" in generated_code
    assert "yield _item" in generated_code

    # Test 1: Sync interface returns async generators (wrapped)
    # Note: For nested generators in return values, the sync interface still returns
    # async generator objects that need to be iterated asynchronously
    str_gen_async, int_gen_async = generated_wrappers.nested_generators.nested_async_generator(3)

    # Verify they are async generators
    assert hasattr(str_gen_async, "__anext__"), "Should be an async generator"
    assert hasattr(int_gen_async, "__anext__"), "Should be an async generator"

    async def consume_sync_result():
        str_results = []
        async for s in str_gen_async:
            str_results.append(s)

        int_results = []
        async for i in int_gen_async:
            int_results.append(i)

        return str_results, int_results

    str_results, int_results = asyncio.run(consume_sync_result())
    assert str_results == [
        "hello",
        "hello",
        "hello",
    ], f"Expected ['hello', 'hello', 'hello'], got {str_results}"
    assert int_results == [0, 1, 2], f"Expected [0, 1, 2], got {int_results}"
    print(f"✓ Sync interface (returns async gens): str_gen yielded {str_results}")
    print(f"✓ Sync interface (returns async gens): int_gen yielded {int_results}")

    # Test 2: Async interface - iterate over both generators
    async def test_async():
        str_gen, int_gen = await generated_wrappers.nested_generators.nested_async_generator.aio(2)

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
        str_gen1, int_gen1 = generated_wrappers.nested_generators.nested_async_generator(1)
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
