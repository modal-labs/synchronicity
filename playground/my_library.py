import typing
import weakref

import _my_library

from synchronicity.descriptor import wrapped_function, wrapped_method
from synchronicity.synchronizer import get_synchronizer

# Wrapper cache for Bar to preserve identity
_cache_Bar: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def _wrap_Bar(impl_instance: _my_library.Bar) -> "Bar":
    """Wrap an implementation instance, preserving identity via weak reference cache."""
    # Use id() as cache key since impl instances are Python objects
    cache_key = id(impl_instance)

    # Check cache first
    if cache_key in _cache_Bar:
        return _cache_Bar[cache_key]

    # Create new wrapper using __new__ to bypass __init__
    wrapper = Bar.__new__(Bar)
    wrapper._impl_instance = impl_instance

    # Cache it
    _cache_Bar[cache_key] = wrapper

    return wrapper


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
    ) -> typing.AsyncGenerator[int, None]:
        impl_function = _my_library.foo
        gen = impl_function()
        async for item in self._synchronizer._run_generator_async(gen):
            yield item


@wrapped_function(_foo)
def foo() -> typing.Generator[int, None, None]:
    impl_function = _my_library.foo
    gen = impl_function()
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

    async def aio(self, s: str) -> typing.AsyncGenerator[str, None]:
        impl_function = _my_library.Bar.moo
        gen = impl_function(self._impl_instance, s)
        async for item in self._synchronizer._run_generator_async(gen):
            yield item


class Bar:
    """Wrapper class for _my_library.Bar with sync/async method support"""

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
        impl_function = _my_library.Bar.moo
        gen = impl_function(self._impl_instance, s)
        yield from self._synchronizer._run_generator_sync(gen)


class _accepts_bar:
    _synchronizer = get_synchronizer("my_library")
    _impl_function = _my_library.accepts_bar
    _sync_wrapper_function: typing.Callable[..., typing.Any]

    def __init__(self, sync_wrapper_function: typing.Callable[..., typing.Any]):
        self._sync_wrapper_function = sync_wrapper_function

    def __call__(self, b: Bar) -> Bar:
        return self._sync_wrapper_function(b)

    async def aio(self, b: Bar) -> Bar:
        impl_function = _my_library.accepts_bar
        b_impl = b._impl_instance
        result = await impl_function(b_impl)
        return _wrap_Bar(result)


@wrapped_function(_accepts_bar)
def accepts_bar(b: Bar) -> Bar:
    impl_function = _my_library.accepts_bar
    b_impl = b._impl_instance
    result = get_synchronizer("my_library")._run_function_sync(impl_function(b_impl))
    return _wrap_Bar(result)
