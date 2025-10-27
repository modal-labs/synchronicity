"""Integration tests for executing generated wrapper code.

Tests that generated code can be imported and executed correctly,
including type translation, caching, and async execution.
"""

import asyncio


def test_generated_code_execution_simple(generated_wrappers):
    """Test that generated code can be imported and executed."""
    # Test the wrapper function
    result = generated_wrappers.simple_function.simple_add(5, 3)
    assert result == 8, f"Expected 8, got {result}"

    print("✓ Generated code execution test passed")


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


def test_generated_code_execution_with_translation(generated_wrappers):
    """Test that type translation works at runtime."""
    # Create a node
    node = generated_wrappers.class_with_translation.create_node(42)
    assert node.value == 42, f"Expected node.value=42, got {node.value}"

    # Create a child node
    child = node.create_child(99)
    assert child.value == 99, f"Expected child.value=99, got {child.value}"

    # Connect nodes - this tests that wrapped objects can be passed as arguments
    result_parent, result_child = generated_wrappers.class_with_translation.connect_nodes(node, child)
    assert result_parent.value == 42, "Expected result_parent.value=42"
    assert result_child.value == 99, "Expected result_child.value=99"

    # Verify identity is preserved through translation
    assert result_parent is node, "Identity should be preserved"
    assert result_child is child, "Identity should be preserved"

    print("✓ Generated code with translation execution test passed")


def test_wrapper_identity_preservation(generated_wrappers):
    """Test that wrapper identity is preserved through translation."""
    # Create a node
    node = generated_wrappers.class_with_translation.create_node(1)

    # Pass through a function that should preserve identity
    returned_node, _ = generated_wrappers.class_with_translation.connect_nodes(node, node)

    # Verify identity is preserved when passing through wrapper boundary
    assert returned_node is node, "Wrapper identity should be preserved through function calls"

    print("✓ Wrapper identity preservation test passed")


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


def test_event_loop_execution(generated_wrappers):
    """Test that .aio() methods run in the synchronizer's event loop."""

    # Test 1: Function .aio()
    async def test_function_aio():
        result = await generated_wrappers.event_loop_check.async_function.aio(5)
        return result

    result1 = asyncio.run(test_function_aio())
    assert result1 == 10, f"Expected 10, got {result1}"
    print(f"✓ Function .aio() runs in synchronizer event loop: {result1}")

    # Test 2: Generator function .aio()
    async def test_generator_aio():
        results = []
        async for val in generated_wrappers.event_loop_check.async_generator.aio(3):
            results.append(val)
        return results

    result2 = asyncio.run(test_generator_aio())
    assert result2 == [0, 1, 2], f"Expected [0, 1, 2], got {result2}"
    print(f"✓ Generator function .aio() runs in synchronizer event loop: {result2}")

    # Test 3: Method .aio()
    checker = generated_wrappers.event_loop_check.EventLoopChecker(10)

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


def test_two_way_generator_send(generated_wrappers):
    """Test that two-way generators (using send()) work correctly across sync/async boundary.

    Two-way generators can receive values via send() method. This test verifies that:
    1. The send() functionality is preserved in the sync wrapper
    2. The asend() functionality works in the async wrapper
    3. State is maintained correctly across send() calls
    4. Type annotations correctly reflect AsyncGenerator[YieldType, SendType]
    """
    # Verify helper functions use send() (not simple iteration)
    generated_code = generated_wrappers.generated_code["generated.two_way_generator"]
    assert "@staticmethod" in generated_code
    assert "asend(_sent)" in generated_code or ".send(_sent)" in generated_code
    print("✓ Generated helpers use send() for bidirectional communication")

    # Test 1: Echo generator with sync interface
    print("\n=== Test 1: Echo generator (sync interface) ===")

    gen = generated_wrappers.two_way_generator.echo_generator()
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
        gen = generated_wrappers.two_way_generator.echo_generator.aio()

        first = await gen.asend(None)
        assert first == "Ready", f"Expected 'Ready', got {first}"

        echo1 = await gen.asend("Async")
        assert echo1 == "Echo: Async", f"Expected 'Echo: Async', got {echo1}"

        await gen.aclose()

    asyncio.run(test_echo_async())
    print("✓ Echo generator async interface works correctly")

    # Test 3: Accumulator generator (stateful)
    print("\n=== Test 3: Accumulator generator (stateful) ===")

    gen = generated_wrappers.two_way_generator.accumulator_generator()

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

    gen = generated_wrappers.two_way_generator.multiplier_generator(3)

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
    from test.support_files import two_way_generator_impl

    print("\n=== Testing aclose() forwarding ===")

    # Test 1: Async interface (aclose)
    print("\n--- Test 1: Async interface with aclose() ---")

    async def test_async_aclose():
        import time

        # Get the wrapped generator via .aio()
        gen = generated_wrappers.test_aclose.generator_with_cleanup.aio()

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
    gen = generated_wrappers.test_aclose.generator_with_cleanup()

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
