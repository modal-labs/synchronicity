import asyncio
import pytest
from inspect import get_annotations
from typing import Any, Dict

from synchronicity import classproperty


@pytest.mark.asyncio
async def test_getattr(synchronizer):
    class Foo:
        _attrs: Dict[str, Any]

        def __init__(self):
            self._attrs = {}

        async def __getattr__(self, k):
            await asyncio.sleep(0.01)
            return self._attrs[k]

        def __setattr__(self, k, v):
            annotations = get_annotations(type(self))
            if k in annotations:
                # Only needed because the constructor sets _attrs
                self.__dict__[k] = v
            else:
                self._attrs[k] = v

        @property
        def z(self):
            return self._attrs["x"]

        @staticmethod
        def make_foo():
            return Foo()

        @classproperty
        def my_cls_prop(cls):
            return "abc"

        @classproperty
        async def another_cls_prop(cls):
            await asyncio.sleep(0.01)
            return "another-cls-prop"

    foo = Foo()
    foo.x = 42
    assert await foo.x == 42
    with pytest.raises(KeyError):
        await foo.y
    assert foo.z == 42
    assert Foo.my_cls_prop == "abc"
    assert await Foo.another_cls_prop == "another-cls-prop"

    BlockingFoo = synchronizer.create_blocking(Foo)

    blocking_foo = BlockingFoo()
    blocking_foo.x = 43
    assert blocking_foo.x == 43
    with pytest.raises(KeyError):
        blocking_foo.y
    assert blocking_foo.z == 43
    assert BlockingFoo.my_cls_prop == "abc"
    assert BlockingFoo.another_cls_prop == "another-cls-prop"

    blocking_foo = BlockingFoo.make_foo()
    blocking_foo.x = 44
    assert isinstance(blocking_foo, BlockingFoo)

    # TODO: there is no longer a way to make async properties, but there is this w/ async __getattr__:
    assert await blocking_foo.__getattr__.aio("x") == 44
