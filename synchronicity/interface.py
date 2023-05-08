import enum


class Interface(enum.Enum):
    BLOCKING = enum.auto()
    ASYNC = enum.auto()
    _ASYNC_WITH_BLOCKING_TYPES = enum.auto()  # temporary internal type until we deprecate the old ASYNC type, used for `function.aio` async callables accepting/returning BLOCKING types
    AUTODETECT = enum.auto()  # DEPRECATED
