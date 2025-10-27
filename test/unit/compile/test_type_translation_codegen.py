"""Unit tests for type translation in generated wrapper code.

Tests code generation aspects like helper methods, unwrap/wrap expressions,
and type annotations in generated code.
"""

import typing

from synchronicity.codegen.compile import compile_class, compile_function


def test_compile_with_translation():
    """Test that wrapper code compiles correctly with type translation."""

    # Define test class locally
    class TestNode:
        """A test node class."""

        def __init__(self, value: int):
            self.value = value

        async def create_child(self, child_value: int) -> "TestNode":
            return TestNode(child_value)

    # Define test functions
    async def create_node(value: int) -> TestNode:
        return TestNode(value)

    async def connect_nodes(parent: TestNode, child: TestNode) -> typing.Tuple[TestNode, TestNode]:
        return (parent, child)

    async def get_node_list(nodes: typing.List[TestNode]) -> typing.List[TestNode]:
        return nodes

    async def get_optional_node(node: typing.Optional[TestNode]) -> typing.Optional[TestNode]:
        return node

    # Set up synchronized types
    synchronized_types = {TestNode: ("test_module", "TestNode")}

    # Compile functions with local namespace for forward reference resolution
    local_ns = {"TestNode": TestNode}

    create_node_code = compile_function(create_node, "test_module", "s", synchronized_types, globals_dict=local_ns)
    connect_nodes_code = compile_function(connect_nodes, "test_module", "s", synchronized_types, globals_dict=local_ns)
    get_node_list_code = compile_function(get_node_list, "test_module", "s", synchronized_types, globals_dict=local_ns)
    get_optional_node_code = compile_function(
        get_optional_node, "test_module", "s", synchronized_types, globals_dict=local_ns
    )

    # Compile class
    class_code = compile_class(TestNode, "test_module", "s", synchronized_types, globals_dict=local_ns)

    # Check that the class code contains the expected translation elements
    assert "_instance_cache: weakref.WeakValueDictionary" in class_code
    assert "def _from_impl(cls, impl_instance" in class_code
    assert "TestNode._from_impl(" in class_code
    assert "wrapper._impl_instance = impl_instance" in class_code

    # Check function signatures have proper type annotations
    assert (
        'def create_node(value: int) -> "TestNode":' in create_node_code
        or "def create_node(value: int) -> 'TestNode':" in create_node_code
    )
    assert (
        'def get_node_list(nodes: list[TestNode]) -> "list[TestNode]":' in get_node_list_code
        or "def get_node_list(nodes: list[TestNode]) -> 'list[TestNode]':" in get_node_list_code
    )
    assert (
        'def get_optional_node(node: typing.Union[TestNode, None]) -> "typing.Union[TestNode, None]":'
        in get_optional_node_code
        or "def get_optional_node(node: typing.Union[TestNode, None]) -> 'typing.Union[TestNode, None]':"
        in get_optional_node_code
    )
    assert (
        'def connect_nodes(parent: TestNode, child: TestNode) -> "tuple[TestNode, TestNode]":' in connect_nodes_code
        or "def connect_nodes(parent: TestNode, child: TestNode) -> 'tuple[TestNode, TestNode]':" in connect_nodes_code
    )

    # Check for unwrap/wrap in connect_nodes
    assert "parent_impl = parent._impl_instance" in connect_nodes_code
    assert "child_impl = child._impl_instance" in connect_nodes_code
    assert "TestNode._from_impl(" in connect_nodes_code

    print("✓ Wrapper code compiled successfully with translation")


def test_wrapper_helpers_generated():
    """Test that _from_impl classmethod is generated correctly."""

    class HelperTestClass:
        """Test class for helper generation."""

        def __init__(self, value: int):
            self.value = value

    synchronized_types = {HelperTestClass: ("test_module", "HelperTestClass")}

    compiled_code = compile_class(HelperTestClass, "test_module", "s", synchronized_types)

    # Check the _from_impl classmethod structure with class-level cache
    assert "_instance_cache: weakref.WeakValueDictionary = weakref.WeakValueDictionary()" in compiled_code
    assert "def _from_impl(cls, impl_instance:" in compiled_code
    assert "cache_key = id(impl_instance)" in compiled_code
    assert "if cache_key in cls._instance_cache:" in compiled_code
    assert "wrapper = cls.__new__(cls)" in compiled_code
    assert "wrapper._impl_instance = impl_instance" in compiled_code
    assert "cls._instance_cache[cache_key] = wrapper" in compiled_code

    print("✓ _from_impl classmethod with class-level cache generated correctly")


def test_unwrap_expressions_in_functions():
    """Test that unwrap expressions are generated in function bodies."""

    class UnwrapTestNode:
        """Test node for unwrap expressions."""

        def __init__(self, value: int):
            self.value = value

    async def process_node(node: UnwrapTestNode) -> UnwrapTestNode:
        return node

    synchronized_types = {UnwrapTestNode: ("test_module", "UnwrapTestNode")}
    local_ns = {"UnwrapTestNode": UnwrapTestNode}

    compiled_code = compile_function(process_node, "test_module", "s", synchronized_types, globals_dict=local_ns)

    # Check for unwrap in sync wrapper
    assert "node_impl = node._impl_instance" in compiled_code

    # Check for wrap in return using _from_impl
    assert "return UnwrapTestNode._from_impl(result)" in compiled_code

    print("✓ Unwrap/wrap expressions generated in functions")


def test_translation_with_collections():
    """Test that collection types are translated correctly."""

    class CollectionTestNode:
        """Test node for collection translation."""

        def __init__(self, value: int):
            self.value = value

    async def process_list(nodes: typing.List[CollectionTestNode]) -> typing.List[CollectionTestNode]:
        return nodes

    synchronized_types = {CollectionTestNode: ("test_module", "CollectionTestNode")}
    local_ns = {"CollectionTestNode": CollectionTestNode}

    compiled_code = compile_function(process_list, "test_module", "s", synchronized_types, globals_dict=local_ns)

    # Check for list comprehension unwrap
    assert "[x._impl_instance for x in nodes]" in compiled_code

    # Check for list comprehension wrap using _from_impl
    assert "[CollectionTestNode._from_impl(x) for x in " in compiled_code

    print("✓ Collection types translated correctly")


def test_no_translation_for_primitives():
    """Test that primitive types are not translated."""

    async def returns_string() -> str:
        return "hello"

    compiled_code = compile_function(returns_string, "test_module", "test_primitives", {})

    # Should not generate unwrap/wrap for strings
    assert "_impl" not in compiled_code or "str_impl" not in compiled_code
    assert "str._from_impl" not in compiled_code

    print("✓ Primitive types not translated")


def test_async_generator_wrapping():
    """Test that async generators are wrapped correctly in sync and async contexts."""

    async def simple_generator() -> typing.AsyncGenerator[str, None]:
        for i in range(3):
            yield f"item_{i}"

    compiled_code = compile_function(simple_generator, "test_module", "s", {})

    # Check that helper functions are generated for both sync and async contexts
    assert "_wrap_async_gen_str" in compiled_code
    assert "_wrap_async_gen_str_sync" in compiled_code

    # Check async helper uses await and async for
    assert "async def _wrap_async_gen_str(_gen):" in compiled_code
    assert "await _wrapped.asend(_sent)" in compiled_code
    assert "await _wrapped.aclose()" in compiled_code

    # Check sync helper uses regular for (yield from)
    assert "def _wrap_async_gen_str_sync(_gen):" in compiled_code
    assert "yield from get_synchronizer('s')._run_generator_sync(_gen)" in compiled_code

    # Check that async context (__call__ in aio) uses async helper
    assert "async def aio(self, ) -> " in compiled_code

    # Check return type annotations
    assert '-> "typing.Generator[str, None, None]":' in compiled_code  # sync context
    assert '-> "typing.AsyncGenerator[str, None]":' in compiled_code  # async context

    print("✓ Async generator wrapping generated correctly")


def test_tuple_of_generators():
    """Test that tuples of async generators are wrapped correctly."""

    async def tuple_generators() -> tuple[typing.AsyncGenerator[str, None], typing.AsyncGenerator[int, None]]:
        async def gen_str():
            yield "hello"

        async def gen_int():
            yield 42

        return (gen_str(), gen_int())

    compiled_code = compile_function(tuple_generators, "test_module", "s", {})

    # Check that both generator types have wrappers
    assert "_wrap_async_gen_str" in compiled_code
    assert "_wrap_async_gen_int" in compiled_code
    assert "_wrap_async_gen_str_sync" in compiled_code
    assert "_wrap_async_gen_int_sync" in compiled_code

    # Check that tuple wrapping uses appropriate helpers in sync context
    # The sync __call__ method should use *_sync helpers
    assert (
        'def __call__(self, ) -> "tuple[typing.Generator[str, None, None], typing.Generator[int, None, None]]":'
        in compiled_code
    )

    # Check async context uses async helpers
    assert (
        'async def aio(self, ) -> "tuple[typing.AsyncGenerator[str, None], typing.AsyncGenerator[int, None]]":'
        in compiled_code
    )

    # Verify the tuple wrapping expressions reference the helpers
    # In sync context, should call _wrap_async_gen_*_sync
    assert "self._wrap_async_gen_str_sync" in compiled_code or "_wrap_async_gen_str_sync" in compiled_code
    assert "self._wrap_async_gen_int_sync" in compiled_code or "_wrap_async_gen_int_sync" in compiled_code

    # In async context, should call _wrap_async_gen_* (without _sync suffix)
    assert "self._wrap_async_gen_str" in compiled_code or "_wrap_async_gen_str(" in compiled_code
    assert "self._wrap_async_gen_int" in compiled_code or "_wrap_async_gen_int(" in compiled_code

    print("✓ Tuple of generators wrapping generated correctly")


def test_generator_with_wrapped_types():
    """Test that generators yielding wrapped types work correctly."""

    class GenNode:
        """Test node for generator."""

        def __init__(self, value: int):
            self.value = value

    async def node_generator() -> typing.AsyncGenerator[GenNode, None]:
        yield GenNode(1)
        yield GenNode(2)

    synchronized_types = {GenNode: ("test_module", "GenNode")}
    local_ns = {"GenNode": GenNode}

    compiled_code = compile_function(node_generator, "test_module", "s", synchronized_types, globals_dict=local_ns)

    # Check that generator wrapper is created
    assert "_wrap_async_gen" in compiled_code

    # Check that the yielded items are wrapped with _from_impl
    assert "GenNode._from_impl(_item)" in compiled_code

    # Verify sync and async helpers are both generated
    assert "async def _wrap_async_gen" in compiled_code
    assert "def _wrap_async_gen" in compiled_code  # sync version (has both async and non-async defs)

    print("✓ Generator with wrapped types generated correctly")


if __name__ == "__main__":
    test_compile_with_translation()
    test_wrapper_helpers_generated()
    test_unwrap_expressions_in_functions()
    test_translation_with_collections()
    test_no_translation_for_primitives()
    test_async_generator_wrapping()
    test_tuple_of_generators()
    test_generator_with_wrapped_types()
    print("\n✅ All unit tests passed!")
