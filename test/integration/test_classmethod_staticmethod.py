"""Integration tests for classmethod and staticmethod wrapping."""

import asyncio
from pathlib import Path

from test.integration.test_utils import check_pyright


def test_instance_method(generated_wrappers):
    """Test that instance methods still work."""
    import test_support

    obj = test_support.TestClass(42)
    result = obj.instance_method()
    assert result == 42

    # Test async version
    async def test_async():
        result = await obj.instance_method.aio()
        assert result == 42

    asyncio.run(test_async())


def test_async_classmethod(generated_wrappers):
    """Test async classmethod."""
    import test_support

    result = test_support.TestClass.async_classmethod(2)
    assert result == 84

    # Test async version
    async def test_async():
        result = await test_support.TestClass.async_classmethod.aio(3)
        assert result == 126

    asyncio.run(test_async())


def test_sync_classmethod(generated_wrappers):
    """Test sync classmethod."""
    import test_support

    result = test_support.TestClass.sync_classmethod("test")
    assert result == "sync_test"


def test_async_staticmethod(generated_wrappers):
    """Test async staticmethod."""
    import test_support

    result = test_support.TestClass.async_staticmethod(10, 20)
    assert result == 30

    # Test async version
    async def test_async():
        result = await test_support.TestClass.async_staticmethod.aio(15, 25)
        assert result == 40

    asyncio.run(test_async())


def test_sync_staticmethod(generated_wrappers):
    """Test sync staticmethod."""
    import test_support

    result = test_support.TestClass.sync_staticmethod("hello")
    assert result == "static_hello"


def test_pyright_classmethod_staticmethod(generated_wrappers):
    """Test that generated classmethod and staticmethod code passes pyright."""
    import test_support

    # Verify type correctness with pyright
    # Note: reportGeneralTypeIssues is set to "warning" in pyproject.toml
    # to handle false positives from dummy method definitions
    check_pyright([Path(test_support.__file__)])


def test_pyright_type_inference_classmethod_staticmethod(generated_wrappers, support_files):
    """Test that classmethod and staticmethod type inference works correctly with pyright."""
    type_check_file = support_files / "type_check_classmethod_staticmethod.py"

    output = check_pyright([type_check_file])
    print(f"Pyright output:\n{output}")

    # Verify type inference for sync classmethod
    assert 'Type of "result1" is "str"' in output

    # Verify type inference for sync staticmethod
    assert 'Type of "result2" is "str"' in output

    # Verify type inference for async classmethod (sync interface)
    assert 'Type of "result3" is "int"' in output

    # Verify type inference for async staticmethod (sync interface)
    assert 'Type of "result4" is "int"' in output

    # Verify type inference for async classmethod aio
    assert 'Type of "result5" is "int"' in output or 'Type of "result5" is "CoroutineType[Any, Any, int]"' in output

    # Verify type inference for async staticmethod aio
    assert 'Type of "result6" is "int"' in output or 'Type of "result6" is "CoroutineType[Any, Any, int]"' in output

    print("✓ Pyright type checking for classmethod/staticmethod: Passed")
