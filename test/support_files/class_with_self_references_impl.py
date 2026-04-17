import typing

from synchronicity import Module

lib = Module("class_with_self_references")


@lib.wrap_class()
class SomeClass:
    def accept_self(self, s: typing.Self) -> typing.Self:
        assert type(s) is type(self)
        return self

    def accept_self_by_name(self, s: "SomeClass") -> "SomeClass":
        assert isinstance(s, SomeClass)  # this can be a subclass too
        return self


@lib.wrap_class()
class SomeSubclass(SomeClass):
    """Empty subclass: inherited Self-typed methods should use the subclass as Self."""
