"""Integration tests for callback_translation_impl.py support file."""

from pathlib import Path

from test.integration.test_utils import check_pyright


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

    def make_node(x: int) -> callback_translation.Node:
        return callback_translation.Node(x)

    listified = callback_translation.listify(make_node)
    listified_result = listified(3)
    assert [item.value for item in listified_result] == [3]
    assert all(isinstance(item, callback_translation.Node) for item in listified_result)


def test_pyright_implementation():
    import callback_translation_impl

    check_pyright([Path(callback_translation_impl.__file__)])


def test_pyright_wrapper():
    import callback_translation

    check_pyright([Path(callback_translation.__file__)])


def test_pyright_usage():
    from importlib.util import find_spec

    spec = find_spec("callback_translation_typecheck")
    assert spec and spec.origin
    check_pyright([Path(spec.origin)])
