import synchronicity

m = synchronicity.Module("class_with_inheritance")


class UnwrappedBase:
    a: int

    def __init__(self):
        self.a = 1

    def unwrapped_method(self) -> bool:
        return True


@m.wrap_class
class WrappedBase(UnwrappedBase):
    b: str

    def __init__(self):
        super().__init__()
        self.b = "hello"

    async def wrapped_method(self) -> list:
        return []


@m.wrap_class
class WrappedSub(WrappedBase):
    c: float

    def __init__(self):
        super().__init__()
        self.c = 1.5

    async def wrapped_in_sub(self) -> dict:
        return {}
