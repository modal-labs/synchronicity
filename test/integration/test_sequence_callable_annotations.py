"""Integration tests for Sequence translation."""

from pathlib import Path

from test.integration.test_utils import check_pyright


def test_runtime():
    import sequence_callable_annotations
    import sequence_callable_annotations_impl

    nodes = [sequence_callable_annotations.Node(1), sequence_callable_annotations.Node(2)]
    cloned = sequence_callable_annotations.clone_all(nodes)

    assert [node.value for node in cloned] == [1, 2]
    assert all(isinstance(node, sequence_callable_annotations.Node) for node in cloned)

    callback = sequence_callable_annotations.make_callback(nodes[0])
    callback_result = callback()
    assert all(isinstance(node, sequence_callable_annotations_impl.Node) for node in callback_result)


def test_generated_wrapper_source():
    import sequence_callable_annotations

    wrapper_source = Path(sequence_callable_annotations.__file__).read_text()

    assert 'def clone_all(nodes: "typing.Sequence[Node]") -> "typing.Sequence[Node]":' in wrapper_source
    assert (
        'def make_callback(node: "Node") -> "typing.Callable[..., '
        'typing.Sequence[sequence_callable_annotations_impl.Node]]":' in wrapper_source
    )


def test_pyright_implementation():
    import sequence_callable_annotations_impl

    check_pyright([Path(sequence_callable_annotations_impl.__file__)])


def test_pyright_wrapper():
    import sequence_callable_annotations

    check_pyright([Path(sequence_callable_annotations.__file__)])


def test_pyright_usage():
    import sequence_callable_annotations_typecheck

    check_pyright([Path(sequence_callable_annotations_typecheck.__file__)])
