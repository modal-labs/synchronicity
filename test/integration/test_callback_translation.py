"""Integration tests for callback_translation_impl.py support file."""

import pytest
from pathlib import Path

from test.integration.test_utils import check_pyright


@pytest.mark.xfail(
    strict=True,
    reason="Callback parameters and returns that mention wrapped types are not translated yet",
)
def test_runtime():
    import callback_translation

    node = callback_translation.Node(1)

    def clone_node(value: callback_translation.Node) -> callback_translation.Node:
        assert isinstance(value, callback_translation.Node)
        return callback_translation.Node(value.value + 1)

    def read_node(value: callback_translation.Node) -> int:
        assert isinstance(value, callback_translation.Node)
        return value.value

    assert callback_translation.apply_to_node(node, clone_node).value == 2
    assert callback_translation.map_node_to_int(node, read_node) == 1


def test_pyright_implementation():
    import callback_translation_impl

    check_pyright([Path(callback_translation_impl.__file__)])


@pytest.mark.xfail(
    strict=True,
    reason="Callback and callable annotations that mention wrapped types are not typed correctly yet",
)
def test_pyright_wrapper():
    import callback_translation

    check_pyright([Path(callback_translation.__file__)])


@pytest.mark.xfail(
    strict=True,
    reason="Callback and callable annotations that mention wrapped types are not typed correctly yet",
)
def test_pyright_usage():
    from importlib.util import find_spec

    spec = find_spec("callback_translation_typecheck")
    assert spec and spec.origin
    check_pyright([Path(spec.origin)])
