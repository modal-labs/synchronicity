"""Integration tests for simple_function_impl.py support file."""

from pathlib import Path

from test.integration.test_utils import check_pyright


def test_runtime():
    import simple_function

    assert simple_function.simple_add(5, 3) == 8
    assert simple_function.greet() == "hello"
    assert simple_function.greet("goodbye") == "goodbye"
    assert list(simple_function.simple_generator()) == [0, 1, 2]
    assert simple_function.returns_awaitable() == "hello"


def test_pyright_implementation():
    import simple_function_impl

    check_pyright([Path(simple_function_impl.__file__)])


def test_pyright_wrapper():
    import simple_function

    check_pyright([Path(simple_function.__file__)])


def test_pyright_usage():
    from importlib.util import find_spec

    spec = find_spec("simple_function_typecheck")
    assert spec and spec.origin
    check_pyright([Path(spec.origin)])
