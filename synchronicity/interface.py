import enum


class Interface(enum.Enum):
    BLOCKING = enum.auto()
    ASYNC = enum.auto()
    AUTODETECT = enum.auto()  # DEPRECATED
