"""Consumer typing checks for class_with_inheritance wrappers."""

from typing import assert_type

import class_with_inheritance


def _usage() -> None:
    base = class_with_inheritance.WrappedBase(b="foo")
    sub = class_with_inheritance.WrappedSub(b="bar")
    assert_type(base, class_with_inheritance.WrappedBase)
    assert_type(sub, class_with_inheritance.WrappedSub)

    wt = class_with_inheritance.WrappedType()
    out = sub.wrapped_method(t=wt)
    assert_type(out, list)

    plain = class_with_inheritance.ClassWithoutOwnMethods("hello")
    assert_type(plain.wrapped_method(wt), list)
