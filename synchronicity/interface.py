import enum


class Interface(enum.Enum):
    AUTODETECT = enum.auto()
    BLOCKING = enum.auto()
    ASYNC = enum.auto()
