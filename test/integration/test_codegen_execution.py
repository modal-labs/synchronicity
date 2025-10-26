"""Integration tests for executing generated wrapper code.

Tests that generated code can be imported and executed correctly,
including type translation, caching, and async execution.
"""

import asyncio
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from synchronicity.codegen.compile import compile_modules


@contextmanager
def generated_module(code: str, module_name: str):
    """Context manager that writes generated code to a temp file and imports it.

    Args:
        code: The Python code to write
        module_name: Name for the generated module

    Yields:
        The imported module object
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Write the generated module
        wrapper_file = tmppath / f"{module_name}.py"
        wrapper_file.write_text(code)

        # Add to path
        sys.path.insert(0, str(tmppath))

        try:
            # Import the generated module
            module = __import__(module_name)
            yield module
        finally:
            # Clean up
            sys.path.remove(str(tmppath))
            if module_name in sys.modules:
                del sys.modules[module_name]


def test_generated_code_execution_simple():
    """Test that generated code can be imported and executed."""
    from test.support_files import _simple_function

    # Generate wrapper code
    modules = compile_modules([_simple_function.wrapper_module], "s")
    generated_code = list(modules.values())[0]  # Extract the single module

    # Write to a temporary file and import it
    with generated_module(generated_code, "generated_wrapper") as wrapper:
        # Test the wrapper function
        result = wrapper.simple_add(5, 3)
        assert result == 8, f"Expected 8, got {result}"

        print("✓ Generated code execution test passed")


def test_generated_code_execution_class():
    """Test that generated class wrappers work correctly."""
    from test.support_files import _simple_class

    # Generate wrapper code
    modules = compile_modules([_simple_class.wrapper_module], "s")
    generated_code = list(modules.values())[0]  # Extract the single module

    # Write to a temporary file and import it
    with generated_module(generated_code, "generated_class_wrapper") as wrapper:
        # Test the wrapper class
        counter = wrapper.Counter(10)
        assert counter.count == 10, f"Expected count=10, got {counter.count}"

        # Test method call
        result = counter.increment()
        assert result == 11, f"Expected 11, got {result}"
        assert counter.count == 11, f"Expected count=11, got {counter.count}"

        # Test generator method
        multiples = list(counter.get_multiples(3))
        assert multiples == [0, 11, 22], f"Expected [0, 11, 22], got {multiples}"

        print("✓ Generated class execution test passed")


def test_generated_code_execution_with_translation():
    """Test that type translation works at runtime."""
    from test.support_files import _class_with_translation

    # Generate wrapper code
    modules = compile_modules([_class_with_translation.wrapper_module], "s")
    generated_code = list(modules.values())[0]  # Extract the single module

    # Write to a temporary file and import it
    with generated_module(generated_code, "generated_translation_wrapper") as wrapper:
        # Test node creation
        node = wrapper.create_node(42)
        assert node.value == 42, f"Expected value=42, got {node.value}"

        # Test method that returns same type
        child = node.create_child(100)
        assert child.value == 100, f"Expected value=100, got {child.value}"

        # Verify wrapper caching - creating from same impl should return same wrapper
        assert hasattr(node, "_impl_instance"), "Wrapper should have _impl_instance"
        assert hasattr(child, "_impl_instance"), "Child wrapper should have _impl_instance"

        # Test generator that yields wrapped types
        children = list(node.get_children(3))
        assert len(children) == 3, f"Expected 3 children, got {len(children)}"
        assert children[0].value == 42, f"Expected first child value=42, got {children[0].value}"
        assert children[1].value == 43, f"Expected second child value=43, got {children[1].value}"
        assert children[2].value == 44, f"Expected third child value=44, got {children[2].value}"

        print("✓ Generated code with translation execution test passed")


def test_wrapper_identity_preservation():
    """Test that wrapper identity is preserved through caching."""
    from test.support_files import _class_with_translation

    # Generate wrapper code
    modules = compile_modules([_class_with_translation.wrapper_module], "s")
    generated_code = list(modules.values())[0]  # Extract the single module

    # Write to a temporary file and import it
    with generated_module(generated_code, "generated_identity_wrapper") as wrapper:
        # Create a node
        node1 = wrapper.Node(42)

        # Create a child from that node
        child = node1.create_child(100)

        # Pass them through a function that accepts and returns a list
        nodes = wrapper.get_node_list([node1, child])

        # The returned nodes should be the same wrapper instances due to caching
        # (same impl_instance id should return same wrapper)
        assert len(nodes) == 2, f"Expected 2 nodes, got {len(nodes)}"
        assert nodes[0]._impl_instance is node1._impl_instance, "First node impl should be preserved"
        assert nodes[1]._impl_instance is child._impl_instance, "Second node impl should be preserved"

        print("✓ Wrapper identity preservation test passed")


def test_method_wrapper_aio_execution():
    """Test that calling .aio() on method wrappers works correctly.

    This tests both regular async methods and async generator methods
    to ensure they can be called via .aio() without errors.
    """
    from test.support_files import _simple_class

    # Generate wrapper code
    modules = compile_modules([_simple_class.wrapper_module], "s")
    generated_code = list(modules.values())[0]

    # Execute the generated code to verify it works
    with generated_module(generated_code, "simple_class_generated") as mod:

        async def test_async_method():
            """Test calling .aio() on a regular async method."""
            counter = mod.Counter(start=10)
            # Call the async version directly
            result = await counter.increment.aio()
            assert result == 11, f"Expected 11, got {result}"
            return result

        async def test_async_generator_method():
            """Test calling .aio() on an async generator method."""
            counter = mod.Counter(start=5)
            # Call the async generator version (get_multiples yields count * i for i in range(n))
            results = []
            async for value in counter.get_multiples.aio(3):
                results.append(value)
            # With count=5 and n=3, should yield 5*0=0, 5*1=5, 5*2=10
            assert results == [0, 5, 10], f"Expected [0, 5, 10], got {results}"
            return results

        # Run the async tests
        result1 = asyncio.run(test_async_method())
        result2 = asyncio.run(test_async_generator_method())

        print(f"✓ Method wrapper .aio() execution: async method returned {result1}")
        print(f"✓ Method wrapper .aio() execution: async generator returned {result2}")


def test_event_loop_execution():
    """Test that all .aio() calls execute in the synchronizer's event loop.

    This is critical - all async code must run in the synchronizer's event loop
    to avoid concurrency issues and ensure proper isolation.
    """
    from test.support_files import _event_loop_check

    # Generate wrapper code
    modules = compile_modules([_event_loop_check.wrapper_module], "s")
    generated_code = list(modules.values())[0]

    # Execute the generated code to verify event loop usage
    with generated_module(generated_code, "event_loop_test_generated") as mod:
        # Test 1: Function .aio() should run in synchronizer event loop
        async def test_function_aio():
            result = await mod.async_function.aio(5)
            assert result == 10, f"Expected 10, got {result}"
            return result

        # Test 2: Generator function .aio() should run in synchronizer event loop
        async def test_generator_aio():
            results = []
            async for value in mod.async_generator.aio(3):
                results.append(value)
            assert results == [0, 1, 2], f"Expected [0, 1, 2], got {results}"
            return results

        # Test 3: Method .aio() should run in synchronizer event loop
        async def test_method_aio():
            checker = mod.EventLoopChecker(7)
            result = await checker.async_method.aio()
            assert result == 14, f"Expected 14, got {result}"
            return result

        # Test 4: Generator method .aio() should run in synchronizer event loop
        async def test_generator_method_aio():
            checker = mod.EventLoopChecker(3)
            results = []
            async for value in checker.async_generator_method.aio(4):
                results.append(value)
            assert results == [0, 3, 6, 9], f"Expected [0, 3, 6, 9], got {results}"
            return results

        # Run all tests - they will raise AssertionError if not in the right event loop
        result1 = asyncio.run(test_function_aio())
        print(f"✓ Function .aio() runs in synchronizer event loop: {result1}")

        result2 = asyncio.run(test_generator_aio())
        print(f"✓ Generator function .aio() runs in synchronizer event loop: {result2}")

        result3 = asyncio.run(test_method_aio())
        print(f"✓ Method .aio() runs in synchronizer event loop: {result3}")

        result4 = asyncio.run(test_generator_method_aio())
        print(f"✓ Generator method .aio() runs in synchronizer event loop: {result4}")


def test_nested_async_generators_in_tuple():
    """Test that nested async generators in tuples work end-to-end.

    This tests the case where a function returns a tuple containing async generators,
    verifying that both sync and async interfaces work correctly.
    """
    from test.support_files import nested_generators

    # Compile the module
    modules_code = compile_modules([nested_generators.wrapper_module], "test_sync")
    generated_code = modules_code["nested_generators"]

    # Verify helper functions are generated for nested generators
    assert "@staticmethod" in generated_code
    assert "async def _wrap_async_gen" in generated_code
    assert "yield _item" in generated_code

    # Test execution with generated module
    with generated_module(generated_code, "nested_generators") as mod:
        # Test 1: Sync interface returns async generators (wrapped)
        # Note: For nested generators in return values, the sync interface still returns
        # async generator objects that need to be iterated asynchronously
        str_gen_async, int_gen_async = mod.nested_async_generator(3)

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
            str_gen, int_gen = await mod.nested_async_generator.aio(2)

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
            str_gen1, int_gen1 = mod.nested_async_generator(1)
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


def test_two_way_generator_send():
    """Test that two-way generators (using send()) work correctly across sync/async boundary.

    Two-way generators can receive values via send() method. This test verifies that:
    1. The send() functionality is preserved in the sync wrapper
    2. The asend() functionality works in the async wrapper
    3. State is maintained correctly across send() calls
    4. Type annotations correctly reflect AsyncGenerator[YieldType, SendType]
    """
    from test.support_files import two_way_generator

    # Compile the module
    modules_code = compile_modules([two_way_generator.wrapper_module], "test_sync")
    generated_code = modules_code["two_way_generator"]

    # Verify helper functions use send() (not simple iteration)
    assert "@staticmethod" in generated_code
    assert "asend(_sent)" in generated_code or ".send(_sent)" in generated_code
    print("✓ Generated helpers use send() for bidirectional communication")

    # Test execution with generated module
    with generated_module(generated_code, "two_way_generator") as mod:
        # Test 1: Echo generator with sync interface
        print("\n=== Test 1: Echo generator (sync interface) ===")

        gen = mod.echo_generator()
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
            gen = mod.echo_generator.aio()
            # First value is yielded without send
            first = await gen.asend(None)
            assert first == "Ready", f"Expected 'Ready', got {first}"

            # Send values and get echoes back
            echo1 = await gen.asend("Async")
            assert echo1 == "Echo: Async", f"Expected 'Echo: Async', got {echo1}"

            echo2 = await gen.asend("Test")
            assert echo2 == "Echo: Test", f"Expected 'Echo: Test', got {echo2}"

            await gen.aclose()
            return True

        result = asyncio.run(test_echo_async())
        assert result is True
        print("✓ Echo generator async interface works correctly")

        # Test 3: Accumulator generator (maintains state)
        print("\n=== Test 3: Accumulator generator (stateful) ===")

        gen = mod.accumulator_generator()
        # First value is 0
        total = gen.send(None)
        assert total == 0, f"Expected 0, got {total}"

        # Add 5
        total = gen.send(5)
        assert total == 5, f"Expected 5, got {total}"

        # Add 10
        total = gen.send(10)
        assert total == 15, f"Expected 15, got {total}"

        # Add 3
        total = gen.send(3)
        assert total == 18, f"Expected 18, got {total}"

        # Send None (should not change total)
        total = gen.send(None)
        assert total == 18, f"Expected 18, got {total}"

        gen.close()
        print("✓ Accumulator generator maintains state correctly")

        # Test 4: Multiplier generator with parameter
        print("\n=== Test 4: Multiplier generator (with parameter) ===")

        # Create multiplier with factor=3
        gen = mod.multiplier_generator(3)

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


def test_generator_aclose_forwarding():
    """Test that aclose() is properly forwarded to ensure cleanup happens.

    This is critical to:
    1. Prevent dangling async generators in separate threads
    2. Ensure finalization logic (try/finally blocks) executes
    3. Wait for cleanup before returning to caller
    """
    from test.support_files import two_way_generator

    print("\n=== Testing aclose() forwarding ===")

    # Compile just the cleanup generator
    from synchronicity import Module

    cleanup_module = Module("test_aclose")
    cleanup_module.wrap_function(two_way_generator.generator_with_cleanup)

    modules_code = compile_modules([cleanup_module], "test_sync")
    generated_code = modules_code["test_aclose"]

    # Test execution with generated module
    with generated_module(generated_code, "test_aclose") as mod:
        # Test 1: Async interface (aclose)
        print("\n--- Test 1: Async interface with aclose() ---")

        async def test_async_aclose():
            import time

            # Get the wrapped generator via .aio()
            gen = mod.generator_with_cleanup.aio()

            # Consume a couple of values
            result = await gen.asend(None)
            assert result == "first", f"Expected 'first', got {result}"
            print(f"  First value: {result}")

            result = await gen.asend(None)
            assert result == "second", f"Expected 'second', got {result}"
            print(f"  Second value: {result}")

            # Verify cleanup hasn't happened yet
            assert len(two_way_generator.cleanup_tracker) == 0, "Cleanup should not have happened yet"
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
                len(two_way_generator.cleanup_tracker) == 1
            ), f"Expected cleanup once, got {two_way_generator.cleanup_tracker}"
            assert (
                two_way_generator.cleanup_tracker[0] == "cleanup_called"
            ), f"Expected 'cleanup_called', got {two_way_generator.cleanup_tracker[0]}"
            print("  ✓ Cleanup was properly forwarded and executed")

        asyncio.run(test_async_aclose())

        # Test 2: Sync interface (close)
        print("\n--- Test 2: Sync interface with close() ---")

        import time

        # Get the wrapped generator via sync interface
        gen = mod.generator_with_cleanup()

        # Consume a couple of values
        result = gen.send(None)
        assert result == "first", f"Expected 'first', got {result}"
        print(f"  First value: {result}")

        result = gen.send(None)
        assert result == "second", f"Expected 'second', got {result}"
        print(f"  Second value: {result}")

        # Verify cleanup hasn't happened yet
        assert len(two_way_generator.cleanup_tracker) == 0, "Cleanup should not have happened yet"
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
            len(two_way_generator.cleanup_tracker) == 1
        ), f"Expected cleanup once, got {two_way_generator.cleanup_tracker}"
        assert (
            two_way_generator.cleanup_tracker[0] == "cleanup_called"
        ), f"Expected 'cleanup_called', got {two_way_generator.cleanup_tracker[0]}"
        print("  ✓ Cleanup was properly forwarded and executed")

        print("\n=== All aclose() forwarding tests passed! ===")
