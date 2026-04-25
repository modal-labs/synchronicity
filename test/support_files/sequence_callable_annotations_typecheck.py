"""Consumer typing checks for Sequence annotations."""

import typing
from typing import assert_type

import sequence_callable_annotations
import sequence_callable_annotations_impl

nodes = [sequence_callable_annotations.Node(1), sequence_callable_annotations.Node(2)]
cloned = sequence_callable_annotations.clone_all(nodes)
assert_type(cloned, typing.Sequence[sequence_callable_annotations.Node])

callback = sequence_callable_annotations.make_callback(nodes[0])
assert_type(callback, typing.Callable[..., typing.Sequence[sequence_callable_annotations_impl.Node]])
