import typing

import _my_library

from synchronicity2.descriptor import wrapped_function, wrapped_method
from synchronicity2.synchronizer import get_synchronizer

NoneType = None


class _foo:
    _synchronizer = get_synchronizer("my_library")
    _impl_function = _my_library.foo
    _sync_wrapper_function: typing.Callable[..., typing.Any]

    def __init__(self, sync_wrapper_function: typing.Callable[..., typing.Any]):
        self._sync_wrapper_function = sync_wrapper_function

    def __call__(
        self,
    ) -> typing.Generator[int, None, None]:
        return self._sync_wrapper_function()

    async def aio(
        self,
    ) -> typing.AsyncGenerator[int, NoneType]:
        gen = _my_library.foo()
        async for item in self._synchronizer._run_generator_async(gen):
            yield item


@wrapped_function(_foo)
def foo() -> typing.Generator[int, None, None]:
    gen = _my_library.foo()
    yield from get_synchronizer("my_library")._run_generator_sync(gen)


class Bar_moo:
    _synchronizer = get_synchronizer("my_library")
    _impl_instance: _my_library.Bar
    _sync_wrapper_method: typing.Callable[..., typing.Any]

    def __init__(self, wrapper_instance: "Bar", unbound_sync_wrapper_method: typing.Callable[..., typing.Any]):
        self._wrapper_instance = wrapper_instance
        self._impl_instance = wrapper_instance._impl_instance
        self._unbound_sync_wrapper_method = unbound_sync_wrapper_method

    def __call__(self, s: str) -> typing.Generator[str, None, None]:
        return self._unbound_sync_wrapper_method(self._wrapper_instance, s)

    async def aio(self, s: str) -> typing.AsyncGenerator[str, NoneType]:
        gen = _my_library.Bar.moo(self._impl_instance, s)
        async for item in self._synchronizer._run_generator_async(gen):
            yield item


class Bar:
    """Wrapper class for my_library.Bar with sync/async method support"""

    _synchronizer = get_synchronizer("my_library")

    def __init__(self, a: str):
        self._impl_instance = _my_library.Bar(a=a)

    # Generated properties
    @property
    def a(self) -> str:
        return self._impl_instance.a

    @a.setter
    def a(self, value: str):
        self._impl_instance.a = value

    @wrapped_method(Bar_moo)
    def moo(self, s: str) -> typing.Generator[str, None, None]:
        gen = _my_library.Bar.moo(self._impl_instance, s)
        yield from self._synchronizer._run_generator_sync(gen)
