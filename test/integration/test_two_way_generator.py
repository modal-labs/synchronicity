"""Integration tests for two_way_generator_impl.py support file.

Tests two-way generators (using send()) and cleanup (aclose forwarding).
"""

import asyncio

from .test_utils import check_pyright


def test_two_way_generator_send(generated_wrappers):
    """Test that two-way generators (using send()) work correctly across sync/async boundary.

    Two-way generators can receive values via send() method. This test verifies that:
    1. The send() functionality is preserved in the sync wrapper
    2. The asend() functionality works in the async wrapper
    3. State is maintained correctly across send() calls
    4. Type annotations correctly reflect AsyncGenerator[YieldType, SendType]
    """
    # Verify helper functions use send() (not simple iteration)
    import two_way_generator

    # Test 1: Echo generator with sync interface
    print("\n=== Test 1: Echo generator (sync interface) ===")

    gen = two_way_generator.echo_generator()
    # First value is yielded without send
    first = gen.send(None)
    assert first == "Ready", f"Expected 'Ready', got {first}"

    # Send values and get echoes back
    echo1 = gen.send("Hello")
    assert echo1 == "Echo: Hello", f"Expected 'Echo: Hello', got {echo1}"

    echo2 = gen.send("World")
    assert echo2 == "Echo: World", f"Expected 'Echo: World', got {echo2}"

    # Test None handling
    echo3 = gen.send(None)
    assert echo3 == "Got None", f"Expected 'Got None', got {echo3}"

    gen.close()
    print("✓ Echo generator sync interface works correctly")

    # Test 2: Echo generator with async interface
    print("\n=== Test 2: Echo generator (async interface) ===")

    async def test_echo_async():
        gen = two_way_generator.echo_generator.aio()

        first = await gen.asend(None)
        assert first == "Ready", f"Expected 'Ready', got {first}"

        echo1 = await gen.asend("Async")
        assert echo1 == "Echo: Async", f"Expected 'Echo: Async', got {echo1}"

        await gen.aclose()

    asyncio.run(test_echo_async())
    print("✓ Echo generator async interface works correctly")

    # Test 3: Accumulator generator (stateful)
    print("\n=== Test 3: Accumulator generator (stateful) ===")

    gen = two_way_generator.accumulator_generator()

    # First yield returns 0
    result = gen.send(None)
    assert result == 0, f"Expected 0, got {result}"

    # Send 5, get sum = 5
    result = gen.send(5)
    assert result == 5, f"Expected 5, got {result}"

    # Send 10, get sum = 15
    result = gen.send(10)
    assert result == 15, f"Expected 15, got {result}"

    # Send None, get same sum
    result = gen.send(None)
    assert result == 15, f"Expected 15, got {result}"

    gen.close()
    print("✓ Accumulator generator maintains state correctly")

    # Test 4: Multiplier generator with parameter
    print("\n=== Test 4: Multiplier generator (with parameter) ===")

    gen = two_way_generator.multiplier_generator(3)

    # First value is 0
    result = gen.send(None)
    assert result == 0, f"Expected 0, got {result}"

    # Send 5, get 15 (5 * 3)
    result = gen.send(5)
    assert result == 15, f"Expected 15, got {result}"

    # Send 7, get 21 (7 * 3)
    result = gen.send(7)
    assert result == 21, f"Expected 21, got {result}"

    # Send None, get 0
    result = gen.send(None)
    assert result == 0, f"Expected 0, got {result}"

    gen.close()
    print("✓ Multiplier generator with parameter works correctly")

    print("\n=== All two-way generator tests passed! ===")


def test_generator_aclose_forwarding(generated_wrappers):
    """Test that aclose() is properly forwarded to ensure cleanup happens.

    This is critical to:
    1. Prevent dangling async generators in separate threads
    2. Ensure finalization logic (try/finally blocks) executes
    3. Wait for cleanup before returning to caller
    """
    import two_way_generator
    import two_way_generator_impl

    print("\n=== Testing aclose() forwarding ===")

    # Test 1: Async interface (aclose)
    print("\n--- Test 1: Async interface with aclose() ---")

    async def test_async_aclose():
        import time

        # Get the wrapped generator via .aio()
        gen = two_way_generator.generator_with_cleanup.aio()

        # Consume a couple of values
        result = await gen.asend(None)
        assert result == "first", f"Expected 'first', got {result}"
        print(f"  First value: {result}")

        result = await gen.asend(None)
        assert result == "second", f"Expected 'second', got {result}"
        print(f"  Second value: {result}")

        # Verify cleanup hasn't happened yet
        assert len(two_way_generator_impl.cleanup_tracker) == 0, "Cleanup should not have happened yet"
        print("  Verified: No cleanup yet")

        # Close the generator and measure time
        start_time = time.time()
        await gen.aclose()
        elapsed_time = time.time() - start_time
        print(f"  Called aclose() (took {elapsed_time:.2f}s)")

        # Verify cleanup took at least 1 second (async operation was awaited)
        assert elapsed_time >= 1.0, f"aclose() should have taken at least 1 second (actual: {elapsed_time:.2f}s)"
        print(f"  ✓ Cleanup was properly awaited (blocked for {elapsed_time:.2f}s)")

        # Verify cleanup happened
        assert (
            len(two_way_generator_impl.cleanup_tracker) == 1
        ), f"Expected cleanup once, got {two_way_generator_impl.cleanup_tracker}"
        assert (
            two_way_generator_impl.cleanup_tracker[0] == "cleanup_called"
        ), f"Expected 'cleanup_called', got {two_way_generator_impl.cleanup_tracker[0]}"
        print("  ✓ Cleanup was properly forwarded and executed")

    asyncio.run(test_async_aclose())

    # Test 2: Sync interface (close)
    print("\n--- Test 2: Sync interface with close() ---")

    import time

    # Get the wrapped generator via sync interface
    gen = two_way_generator.generator_with_cleanup()

    # Consume a couple of values
    result = gen.send(None)
    assert result == "first", f"Expected 'first', got {result}"
    print(f"  First value: {result}")

    result = gen.send(None)
    assert result == "second", f"Expected 'second', got {result}"
    print(f"  Second value: {result}")

    # Verify cleanup hasn't happened yet
    assert len(two_way_generator_impl.cleanup_tracker) == 0, "Cleanup should not have happened yet"
    print("  Verified: No cleanup yet")

    # Close the generator and measure time
    start_time = time.time()
    gen.close()
    elapsed_time = time.time() - start_time
    print(f"  Called close() (took {elapsed_time:.2f}s)")

    # Verify cleanup took at least 1 second (async operation was synchronized)
    assert elapsed_time >= 1.0, f"close() should have taken at least 1 second (actual: {elapsed_time:.2f}s)"
    print(f"  ✓ Cleanup was properly synchronized across threads (blocked for {elapsed_time:.2f}s)")

    # Verify cleanup happened
    assert (
        len(two_way_generator_impl.cleanup_tracker) == 1
    ), f"Expected cleanup once, got {two_way_generator_impl.cleanup_tracker}"
    assert (
        two_way_generator_impl.cleanup_tracker[0] == "cleanup_called"
    ), f"Expected 'cleanup_called', got {two_way_generator_impl.cleanup_tracker[0]}"
    print("  ✓ Cleanup was properly forwarded and executed")

    print("\n=== All aclose() forwarding tests passed! ===")


def test_two_way_generator_pyright(generated_wrappers, support_files):
    check_pyright([support_files / "two_way_generator_typecheck.py"])
