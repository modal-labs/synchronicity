import enum


class Interface(enum.Enum):
    BLOCKING = enum.auto()
    _ASYNC_WITH_BLOCKING_TYPES = enum.auto()
