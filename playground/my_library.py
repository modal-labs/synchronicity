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
        # This is what actually gets called when doing foo(...)
        return self._sync_wrapper_function()

    async def aio(
        self,
    ) -> typing.AsyncGenerator[int, NoneType]:
        gen = _my_library.foo()
        # TODO: two-way generators...
        async for item in self._synchronizer._run_generator_async(gen):
            yield item


@wrapped_function(_my_library.foo, _foo)
def foo() -> typing.Generator[int, None, None]:
    # This is where language servers will navigate when going to definition for foo()
    # For that reason, we put the generated *sync* proxy implementation here with the
    # sync function signature.
    # However, this is *not* what gets immediately called when foo() is called -
    # that goes via the wrapper that in turn calls back to this.
    # This complicated control flow is done in order to maximize code navigation usability.
    # This sync function implementation should be really short for that reason and just delegate
    # calls to the original function + input/output translation
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
        # This is what actually gets called when doing Bar().moo(...)
        return self._unbound_sync_wrapper_method(self._wrapper_instance, s)

    async def aio(self, s: str) -> typing.AsyncGenerator[str, NoneType]:
        gen = _my_library.Bar.moo(self._impl_instance, s)
        # TODO: two-way generators...
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

    @wrapped_method(_my_library.Bar.moo, Bar_moo)  # this adds the .aio variant
    def moo(self, s: str) -> typing.Generator[str, None, None]:
        # This is where language servers will navigate when going to definition for Bar().moo
        # For that reason, we put the generated *sync* proxy implementation here with the
        # sync method signature.
        # However, this is *not* the method that gets immediately called when
        # Bar().moo() is called - that goes via the descriptor that in turn calls back to this
        # This complicated control flow is done in order to maximize code navigation usability.
        # This sync method implementation should be really short for that reason and just delegate
        # calls to the original instance + input/output translation
        gen = _my_library.Bar.moo(self._impl_instance, s)
        yield from self._synchronizer._run_generator_sync(gen)
