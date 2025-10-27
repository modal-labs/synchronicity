"""Unit tests for module-level code generation.

Tests the compile_modules() function and verifies the structure and
content of generated wrapper modules.
"""

from pathlib import Path

from synchronicity.codegen.compile import compile_modules
from synchronicity.codegen.writer import write_modules


def test_simple_function_generation(tmpdir, monkeypatch):
    """Test generation of simple functions without dependencies."""
    from test.support_files import simple_function_impl

    # Generate wrapper code
    modules = compile_modules([simple_function_impl.wrapper_module], "s")
    assert len(modules) == 1
    module_paths = list(write_modules(Path(tmpdir), modules))
    print(module_paths)

    # Verify that files can be imported
    monkeypatch.syspath_prepend(tmpdir)
    simple_function = __import__("simple_function")
    assert simple_function.simple_add(2, 4) == 6

    import inspect

    gen = simple_function.simple_generator()
    assert inspect.isgenerator(gen)
    assert list(gen) == [0, 1, 2]

    print("✓ Simple function generation test passed")


def test_simple_class_generation(tmpdir):
    """Test generation of a simple class without translation needs."""
    from test.support_files import simple_class_impl

    # Generate wrapper code
    modules = compile_modules([simple_class_impl.wrapper_module], "s")
    assert len(modules) == 1

    # Write to temporary directory
    module_paths = list(write_modules(Path(tmpdir), modules))
    assert len(module_paths) > 0

    print("✓ Simple class generation test passed")


def test_class_with_translation_generation(tmpdir):
    """Test generation of classes and functions that need type translation."""
    from test.support_files import class_with_translation_impl

    # Generate wrapper code
    modules = compile_modules([class_with_translation_impl.wrapper_module], "s")
    generated_code = list(modules.values())[0]  # Extract the single module

    # Verify weakref import
    assert "import weakref" in generated_code

    # Verify _from_impl classmethod generation with class-level cache
    assert "def _from_impl(cls, impl_instance: test.support_files.class_with_translation_impl.Node)" in generated_code
    assert "_instance_cache: weakref.WeakValueDictionary" in generated_code
    assert "if cache_key in cls._instance_cache:" in generated_code
    assert "wrapper = cls.__new__(cls)" in generated_code
    assert "wrapper._impl_instance = impl_instance" in generated_code
    assert "cls._instance_cache[cache_key] = wrapper" in generated_code

    # Verify translation in function signatures (with quoted return types for forward reference safety)
    assert (
        'def create_node(value: int) -> "Node":' in generated_code
        or "def create_node(value: int) -> 'Node':" in generated_code
    )
    assert (
        'def connect_nodes(parent: Node, child: Node) -> "tuple[Node, Node]":' in generated_code
        or "def connect_nodes(parent: Node, child: Node) -> 'tuple[Node, Node]':" in generated_code
    )
    assert (
        'def get_node_list(nodes: list[Node]) -> "list[Node]":' in generated_code
        or "def get_node_list(nodes: list[Node]) -> 'list[Node]':" in generated_code
    )
    assert (
        'def get_optional_node(node: typing.Union[Node, None]) -> "typing.Union[Node, None]":' in generated_code
        or "def get_optional_node(node: typing.Union[Node, None]) -> 'typing.Union[Node, None]':" in generated_code
    )

    # Verify unwrap expressions in function bodies
    assert "parent_impl = parent._impl_instance" in generated_code
    assert "child_impl = child._impl_instance" in generated_code
    assert "[x._impl_instance for x in nodes]" in generated_code

    # Verify wrap expressions in function bodies now use _from_impl
    assert "Node._from_impl(result)" in generated_code
    assert "[Node._from_impl(x) for x in result]" in generated_code

    # Verify method translation (quotes can be single or double)
    assert (
        'def create_child(self, child_value: int) -> "Node":' in generated_code
        or "def create_child(self, child_value: int) -> 'Node':" in generated_code
    )
    assert "return Node._from_impl(result)" in generated_code

    # Code should compile
    compile(generated_code, "<string>", "exec")

    # Write to temporary directory
    module_paths = list(write_modules(Path(tmpdir), modules))
    assert len(module_paths) > 0

    print("✓ Class with translation generation test passed")
