import enum


class Interface(enum.Enum):
    BLOCKING = enum.auto()
    ASYNC = enum.auto()
