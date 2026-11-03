import enum

import typing_extensions


class Foo:
    pass


cool: str

P = typing_extensions.ParamSpec("P")


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"
