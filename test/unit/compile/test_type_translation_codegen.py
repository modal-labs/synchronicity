"""Unit tests for type translation in generated wrapper code.

Tests code generation aspects like helper methods, unwrap/wrap expressions,
and type annotations in generated code.
"""

import typing

from synchronicity import Module


def test_compile_with_translation():
    """Test that wrapper code compiles correctly with type translation."""
    from synchronicity.codegen.compile import compile_modules

    # Create a simple test module inline
    test_module = Module("test_translation")

    @test_module.wrap_class
    class TestNode:
        """A test node class."""

        def __init__(self, value: int):
            self.value = value

        async def create_child(self, child_value: int) -> "TestNode":
            return TestNode(child_value)

    # Set module so forward references can be resolved
    TestNode.__module__ = "__main__"
    globals()["TestNode"] = TestNode

    @test_module.wrap_function
    async def create_node(value: int) -> TestNode:
        return TestNode(value)

    @test_module.wrap_function
    async def connect_nodes(parent: TestNode, child: TestNode) -> typing.Tuple[TestNode, TestNode]:
        return (parent, child)

    @test_module.wrap_function
    async def get_node_list(nodes: typing.List[TestNode]) -> typing.List[TestNode]:
        return nodes

    @test_module.wrap_function
    async def get_optional_node(node: typing.Optional[TestNode]) -> typing.Optional[TestNode]:
        return node

    # Compile the library
    modules = compile_modules([test_module], "s")
    compiled_code = list(modules.values())[0]  # Extract the single module

    # Check that the code contains the expected elements
    assert "import weakref" in compiled_code
    assert "_instance_cache" in compiled_code
    assert "def _from_impl(cls, impl_instance" in compiled_code
    assert "parent_impl = parent._impl_instance" in compiled_code
    assert "TestNode._from_impl(" in compiled_code

    # Check that the signatures use wrapper types, not impl types
    # The function signatures should have quoted return types for
    # forward reference safety when they contain wrapper types
    assert (
        'def create_node(value: int) -> "TestNode":' in compiled_code
        or "def create_node(value: int) -> 'TestNode':" in compiled_code
    )
    assert (
        'def get_node_list(nodes: list[TestNode]) -> "list[TestNode]":' in compiled_code
        or "def get_node_list(nodes: list[TestNode]) -> 'list[TestNode]':" in compiled_code
    )
    assert (
        'def get_optional_node(node: typing.Union[TestNode, None]) -> "typing.Union[TestNode, None]":' in compiled_code
        or "def get_optional_node(node: typing.Union[TestNode, None]) -> 'typing.Union[TestNode, None]':"
        in compiled_code
    )
    assert (
        'def connect_nodes(parent: TestNode, child: TestNode) -> "tuple[TestNode, TestNode]":' in compiled_code
        or "def connect_nodes(parent: TestNode, child: TestNode) -> 'tuple[TestNode, TestNode]':" in compiled_code
    )

    print("✓ Wrapper code compiled successfully with translation")
    print(f"✓ Generated {len(compiled_code)} characters of wrapper code")


def test_wrapper_helpers_generated():
    """Test that _from_impl classmethod is generated correctly."""
    from synchronicity.codegen.compile import compile_modules

    test_module = Module("test_helpers")

    @test_module.wrap_class
    class HelperTestClass:
        """Test class for helper generation."""

        def __init__(self, value: int):
            self.value = value

    modules = compile_modules([test_module], "s")
    compiled_code = list(modules.values())[0]  # Extract the single module

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
    from synchronicity.codegen.compile import compile_modules

    test_module = Module("test_unwrap")

    @test_module.wrap_class
    class UnwrapTestNode:
        """Test node for unwrap expressions."""

        def __init__(self, value: int):
            self.value = value

    @test_module.wrap_function
    async def process_node(node: UnwrapTestNode) -> UnwrapTestNode:
        return node

    modules = compile_modules([test_module], "s")
    compiled_code = list(modules.values())[0]  # Extract the single module

    # Check for unwrap in sync wrapper
    assert "node_impl = node._impl_instance" in compiled_code

    # Check for wrap in return using _from_impl
    assert "return UnwrapTestNode._from_impl(result)" in compiled_code

    print("✓ Unwrap/wrap expressions generated in functions")


def test_translation_with_collections():
    """Test that collection types are translated correctly."""
    from synchronicity.codegen.compile import compile_modules

    test_module = Module("test_collections")

    @test_module.wrap_class
    class CollectionTestNode:
        """Test node for collection translation."""

        def __init__(self, value: int):
            self.value = value

    @test_module.wrap_function
    async def process_list(nodes: typing.List[CollectionTestNode]) -> typing.List[CollectionTestNode]:
        return nodes

    modules = compile_modules([test_module], "s")
    compiled_code = list(modules.values())[0]  # Extract the single module

    # Check for list comprehension unwrap
    assert "[x._impl_instance for x in nodes]" in compiled_code

    # Check for list comprehension wrap using _from_impl
    assert "[CollectionTestNode._from_impl(x) for x in " in compiled_code

    print("✓ Collection types translated correctly")


def test_no_translation_for_primitives():
    """Test that primitive types are not translated."""
    from synchronicity.codegen.compile import compile_modules

    test_module = Module("test_primitives")

    @test_module.wrap_function
    async def returns_string() -> str:
        return "hello"

    modules = compile_modules([test_module], "test_primitives")
    compiled_code = list(modules.values())[0]  # Extract the single module

    # Should not generate unwrap/wrap for strings
    assert "_impl" not in compiled_code or "str_impl" not in compiled_code
    assert "str._from_impl" not in compiled_code

    print("✓ Primitive types not translated")


if __name__ == "__main__":
    test_compile_with_translation()
    test_wrapper_helpers_generated()
    test_unwrap_expressions_in_functions()
    test_translation_with_collections()
    test_no_translation_for_primitives()
    print("\n✅ All unit tests passed!")
