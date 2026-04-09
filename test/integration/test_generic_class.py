"""Integration tests for generic_class_impl.py support file."""

import pytest
from pathlib import Path

from test.integration.test_utils import check_pyright


def test_runtime():
    import generic_class

    assert hasattr(generic_class, "Container")
    assert hasattr(generic_class, "FunctionWrapper")

    container_int = generic_class.Container(42)
    container_str = generic_class.Container("hello")
    assert container_int.get() == 42
    assert container_str.get() == "hello"

    container = generic_class.Container(100)
    assert container.get() == 100
    container.set(200)
    assert container.get() == 200

    def add(x: int, y: int) -> int:
        return x + y

    wrapper = generic_class.FunctionWrapper(add)
    assert wrapper.call(5, 10) == 15

    def add2(x: int, y: int) -> int:
        return x + y

    wrapper2 = generic_class.FunctionWrapper(add2)
    assert wrapper2._impl_instance.f == add2

    container3 = generic_class.Container(generic_class.WrappedType())
    assert hasattr(container3, "get")
    assert hasattr(container3, "set")
    wrapper3 = generic_class.FunctionWrapper(lambda x: x)
    assert hasattr(wrapper3, "call")


def test_pyright_implementation():
    import generic_class_impl

    check_pyright([Path(generic_class_impl.__file__)])


@pytest.mark.xfail(
    strict=True,
    reason="Pyright does not yet accept generic Container wrapper passing T into impl Container(value)",
)
def test_pyright_wrapper():
    import generic_class

    check_pyright([Path(generic_class.__file__)])


def test_pyright_usage():
    from importlib.util import find_spec

    spec = find_spec("generic_class_typecheck")
    assert spec and spec.origin
    check_pyright([Path(spec.origin)])
