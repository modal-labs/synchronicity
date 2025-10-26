"""Integration tests for executing generated wrapper code.

Tests that generated code can be imported and executed correctly,
including type translation, caching, and async execution.
"""

import asyncio
import sys
import tempfile
import typing
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
    from synchronicity.module import Module

    # Create test module with nested async generator function
    lib = Module("test_nested_gen")

    @lib.wrap_function
    async def nested_async_generator(
        i: int,
    ) -> tuple[typing.AsyncGenerator[str, None], typing.AsyncGenerator[int, None]]:
        """Return tuple of two async generators."""

        async def f():
            for _ in range(i):
                yield "hello"

        async def g():
            for j in range(i):
                yield j

        return (f(), g())

    # Compile the module
    modules_code = compile_modules([lib], "test_sync")
    generated_code = modules_code["test_nested_gen"]

    # Verify helper functions are generated for nested generators
    assert "@staticmethod" in generated_code
    assert "async def _wrap_async_gen" in generated_code
    assert "yield _item" in generated_code

    # Inject the implementation function into the test module so generated code can import it
    current_module = sys.modules[__name__]
    current_module.nested_async_generator = nested_async_generator

    try:
        # Test execution with generated module
        with generated_module(generated_code, "test_nested_gen") as mod:
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
    finally:
        # Clean up: remove the injected function
        if hasattr(current_module, "nested_async_generator"):
            delattr(current_module, "nested_async_generator")
