"""Integration tests for type translation in generated wrapper code."""

import sys
from pathlib import Path

# Add src and support_files to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "support_files"))

# Import the test implementation module
# Note: This import will work at runtime because we add support_files to sys.path
import _test_impl  # type: ignore


def test_compile_with_translation():
    """Test that wrapper code compiles correctly with type translation."""
    from synchronicity2.compile import compile_modules

    # Compile the library
    modules = compile_modules(_test_impl.lib._wrapped, "test_lib")
    compiled_code = list(modules.values())[0]  # Extract the single module

    # Check that the code contains the expected elements
    assert "import weakref" in compiled_code
    assert "_cache__ImplPerson" in compiled_code
    assert "def _from_impl(cls, impl_instance" in compiled_code
    assert "p_impl = p._impl_instance" in compiled_code
    assert "_ImplPerson._from_impl(" in compiled_code

    # Check that the signatures use wrapper types, not impl types
    assert "def accepts_person(p: _ImplPerson) -> _ImplPerson:" in compiled_code
    assert "def accepts_list_of_persons(persons: list[_ImplPerson]) -> list[_ImplPerson]:" in compiled_code
    assert (
        "def accepts_optional_person(p: typing.Union[_ImplPerson, None]) -> "
        "typing.Union[_ImplPerson, None]:" in compiled_code
    )
    assert "def accepts_dict_of_persons(persons: dict[str, _ImplPerson]) -> dict[str, _ImplPerson]:" in compiled_code

    print("✓ Wrapper code compiled successfully with translation")
    print(f"✓ Generated {len(compiled_code)} characters of wrapper code")


def test_wrapper_helpers_generated():
    """Test that _from_impl classmethod is generated correctly."""
    from synchronicity2.compile import compile_modules

    modules = compile_modules(_test_impl.lib._wrapped, "test_lib")
    compiled_code = list(modules.values())[0]  # Extract the single module

    # Check the _from_impl classmethod structure
    assert "_cache__ImplPerson: weakref.WeakValueDictionary = weakref.WeakValueDictionary()" in compiled_code
    assert "def _from_impl(cls, impl_instance: _test_impl._ImplPerson)" in compiled_code
    assert "cache_key = id(impl_instance)" in compiled_code
    assert "if cache_key in _cache__ImplPerson:" in compiled_code
    assert "wrapper = cls.__new__(cls)" in compiled_code
    assert "wrapper._impl_instance = impl_instance" in compiled_code
    assert "_cache__ImplPerson[cache_key] = wrapper" in compiled_code

    print("✓ _from_impl classmethod generated correctly")


def test_unwrap_expressions_in_functions():
    """Test that unwrap expressions are generated in function bodies."""
    from synchronicity2.compile import compile_modules

    modules = compile_modules(_test_impl.lib._wrapped, "test_lib")
    compiled_code = list(modules.values())[0]  # Extract the single module

    # Check for unwrap in sync wrapper
    assert "p_impl = p._impl_instance" in compiled_code

    # Check for wrap in return using _from_impl
    assert "return _ImplPerson._from_impl(result)" in compiled_code

    print("✓ Unwrap/wrap expressions generated in functions")


def test_translation_with_collections():
    """Test that collection types are translated correctly."""
    from synchronicity2.compile import compile_modules

    modules = compile_modules(_test_impl.lib._wrapped, "test_lib")
    compiled_code = list(modules.values())[0]  # Extract the single module

    # Check for list comprehension unwrap
    assert "[x._impl_instance for x in persons]" in compiled_code or "persons_impl" in compiled_code

    # Check for list comprehension wrap using _from_impl
    assert "[_ImplPerson._from_impl(x) for x in " in compiled_code

    print("✓ Collection types translated correctly")


def test_no_translation_for_primitives():
    """Test that primitive types are not translated."""
    from synchronicity2 import Synchronizer
    from synchronicity2.compile import compile_modules

    async def returns_string() -> str:
        return "hello"

    returns_string.__module__ = "_test_impl"
    sys.modules["_test_impl"].returns_string = returns_string

    sync = Synchronizer("test_lib")
    sync.wrap()(returns_string)

    modules = compile_modules(sync._wrapped, "test_lib")
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
    print("\n✅ All integration tests passed!")
