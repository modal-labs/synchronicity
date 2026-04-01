import typing

from synchronicity import Module

lib = Module("class_with_self_references")


@lib.wrap_class
class SomeClass:
    def accept_self(self, s: typing.Self) -> typing.Self:
        assert type(s) is SomeClass
        return self

    def accept_self_by_name(self, s: "SomeClass") -> "SomeClass":
        assert type(s) is SomeClass
        return self
