"""Integration tests for classmethod and staticmethod wrapping."""

import asyncio
from pathlib import Path

from test.integration.test_utils import check_pyright


def test_runtime():
    import classmethod_staticmethod
    import classmethod_staticmethod_impl

    obj = classmethod_staticmethod.TestClass(42)
    assert obj.instance_method() == 42
    assert obj.instance_method.__doc__ == classmethod_staticmethod_impl.TestClass.instance_method.__doc__
    assert obj.instance_method.aio.__doc__ == classmethod_staticmethod_impl.TestClass.instance_method.__doc__

    async def test_async():
        result = await obj.instance_method.aio()
        assert result == 42

    asyncio.run(test_async())

    assert classmethod_staticmethod.TestClass.async_classmethod(2) == 84
    assert (
        classmethod_staticmethod.TestClass.async_classmethod.__doc__
        == classmethod_staticmethod_impl.TestClass.async_classmethod.__doc__
    )
    assert (
        classmethod_staticmethod.TestClass.async_classmethod.aio.__doc__
        == classmethod_staticmethod_impl.TestClass.async_classmethod.__doc__
    )

    async def test_async_cm():
        result = await classmethod_staticmethod.TestClass.async_classmethod.aio(3)
        assert result == 126

    asyncio.run(test_async_cm())

    assert classmethod_staticmethod.TestClass.sync_classmethod("test") == "sync_test"
    assert (
        classmethod_staticmethod.TestClass.sync_classmethod.__doc__
        == classmethod_staticmethod_impl.TestClass.sync_classmethod.__doc__
    )

    assert classmethod_staticmethod.TestClass.async_staticmethod(10, 20) == 30
    assert (
        classmethod_staticmethod.TestClass.async_staticmethod.__doc__
        == classmethod_staticmethod_impl.TestClass.async_staticmethod.__doc__
    )
    assert (
        classmethod_staticmethod.TestClass.async_staticmethod.aio.__doc__
        == classmethod_staticmethod_impl.TestClass.async_staticmethod.__doc__
    )

    async def test_async_sm():
        result = await classmethod_staticmethod.TestClass.async_staticmethod.aio(15, 25)
        assert result == 40

    asyncio.run(test_async_sm())

    assert classmethod_staticmethod.TestClass.sync_staticmethod("hello") == "static_hello"
    assert (
        classmethod_staticmethod.TestClass.sync_staticmethod.__doc__
        == classmethod_staticmethod_impl.TestClass.sync_staticmethod.__doc__
    )


def test_pyright_implementation():
    import classmethod_staticmethod_impl

    check_pyright([Path(classmethod_staticmethod_impl.__file__)])


def test_pyright_wrapper():
    import classmethod_staticmethod

    check_pyright([Path(classmethod_staticmethod.__file__)])


def test_pyright_usage():
    from importlib.util import find_spec

    spec = find_spec("classmethod_staticmethod_typecheck")
    assert spec and spec.origin
    check_pyright([Path(spec.origin)])
