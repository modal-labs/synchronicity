"""Type checking test for classmethod and staticmethod wrappers."""

from typing import reveal_type

import test_support

# Test sync classmethod
result1 = test_support.TestClass.sync_classmethod("test")
reveal_type(result1)  # Should be str

# Test sync staticmethod
result2 = test_support.TestClass.sync_staticmethod("hello")
reveal_type(result2)  # Should be str

# Test async classmethod (sync interface)
result3 = test_support.TestClass.async_classmethod(2)
reveal_type(result3)  # Should be int

# Test async staticmethod (sync interface)
result4 = test_support.TestClass.async_staticmethod(10, 20)
reveal_type(result4)  # Should be int


# Test async classmethod aio
async def test_async_cm():
    result5 = await test_support.TestClass.async_classmethod.aio(3)
    reveal_type(result5)  # Should be int


# Test async staticmethod aio
async def test_async_sm():
    result6 = await test_support.TestClass.async_staticmethod.aio(15, 25)
    reveal_type(result6)  # Should be int
