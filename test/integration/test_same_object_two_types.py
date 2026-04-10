"""Integration tests for same_object_two_types_impl.py support file."""

from pathlib import Path

from test.integration.test_utils import check_pyright


def test_runtime():
    import same_object_two_types

    foo = same_object_two_types.foo_getter()
    bar = same_object_two_types.bar_getter()

    assert isinstance(foo, same_object_two_types.Foo)
    assert isinstance(bar, same_object_two_types.Bar)
    assert foo is bar


def test_pyright_implementation():
    import same_object_two_types_impl

    check_pyright([Path(same_object_two_types_impl.__file__)])


def test_pyright_wrapper():
    import same_object_two_types

    check_pyright([Path(same_object_two_types.__file__)])


def test_pyright_usage():
    from importlib.util import find_spec

    spec = find_spec("same_object_two_types_typecheck")
    assert spec is not None
    assert spec.origin is not None
    check_pyright([Path(spec.origin)])
