"""Integration tests for simple_function_impl.py support file."""

import subprocess
from pathlib import Path

from test.integration.test_utils import check_pyright


def test_runtime():
    import simple_function

    assert simple_function.simple_add(5, 3) == 8
    assert simple_function.greet() == "hello"
    assert simple_function.greet("goodbye") == "goodbye"
    assert simple_function.default_pipe() == subprocess.PIPE
    assert list(simple_function.simple_generator()) == [0, 1, 2]
    assert simple_function.returns_awaitable() == "hello"


def test_generated_wrapper_preserves_source_based_defaults():
    import simple_function

    wrapper_source = Path(simple_function.__file__).read_text()

    assert "import subprocess" in wrapper_source
    assert "def greet(name: str = simple_function_impl.DEFAULT_GREETING) -> str:" in wrapper_source
    assert "def default_pipe(pipe: int = subprocess.PIPE) -> int:" in wrapper_source
    assert '"""Add two numbers asynchronously."""' in wrapper_source
    assert '"""Simple async generator."""' in wrapper_source
    assert '"""Return an awaitable result.\n\nThis docstring should stay multiline.\n"""' in wrapper_source


def test_generated_wrapper_preserves_docstrings():
    import simple_function
    import simple_function_impl

    assert simple_function.simple_add.__doc__ == simple_function_impl.simple_add.__doc__
    assert simple_function.simple_generator.__doc__ == simple_function_impl.simple_generator.__doc__
    assert simple_function.simple_generator.aio.__doc__ == simple_function_impl.simple_generator.__doc__
    assert simple_function.returns_awaitable.__doc__ == simple_function_impl.returns_awaitable.__doc__
    assert simple_function.returns_awaitable.aio.__doc__ == simple_function_impl.returns_awaitable.__doc__


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
