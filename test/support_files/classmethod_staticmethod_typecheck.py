"""Consumer typing checks for classmethod_staticmethod wrappers."""

from typing import assert_type

import classmethod_staticmethod


def _sync_usage() -> None:
    assert_type(classmethod_staticmethod.TestClass.sync_classmethod("test"), str)
    assert_type(classmethod_staticmethod.TestClass.sync_staticmethod("hello"), str)
    assert_type(classmethod_staticmethod.TestClass.async_classmethod(2), int)
    assert_type(classmethod_staticmethod.TestClass.async_staticmethod(10, 20), int)


async def _async_usage() -> None:
    assert_type(await classmethod_staticmethod.TestClass.async_classmethod.aio(3), int)
    assert_type(await classmethod_staticmethod.TestClass.async_staticmethod.aio(15, 25), int)
