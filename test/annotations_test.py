import pytest

from synchronicity.annotations import get_annotations


class MyClass:
    a: int


def my_func(a: str) -> bool:
    return a == "abc"


@pytest.mark.parametrize(
    "obj, expected_annotations",
    [
        (MyClass, {"a": int}),
        (my_func, {"a": str, "return": bool}),
    ],
)
def test_get_annotations(obj, expected_annotations):
    assert get_annotations(obj) == expected_annotations


def test_get_annotations_error():
    with pytest.raises(TypeError):
        get_annotations("abc")
