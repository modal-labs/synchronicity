import typing
import weakref

import _my_library

from synchronicity.descriptor import replace_with, wrapped_method
from synchronicity.synchronizer import get_synchronizer


class Bar_moo:
    def __init__(self, wrapper_instance):
        self._wrapper_instance = wrapper_instance

    def __call__(self, s: str) -> typing.Generator[str, None, None]:
        impl_method = _my_library.Bar.moo
        gen = impl_method(self._wrapper_instance._impl_instance, s)
        yield from self._wrapper_instance._synchronizer._run_generator_sync(gen)

    async def aio(self, s: str) -> typing.AsyncGenerator[str, None]:
        impl_method = _my_library.Bar.moo
        gen = impl_method(self._wrapper_instance._impl_instance, s)
        async for item in self._wrapper_instance._synchronizer._run_generator_async(gen):
            yield item


class Bar:
    """Wrapper class for _my_library.Bar with sync/async method support"""

    _synchronizer = get_synchronizer("my_library")
    _instance_cache: weakref.WeakValueDictionary = weakref.WeakValueDictionary()

    def __init__(self, a: str):
        self._impl_instance = _my_library.Bar(a=a)

    @classmethod
    def _from_impl(cls, impl_instance: _my_library.Bar) -> "Bar":
        """Create wrapper from implementation instance, preserving identity via cache."""
        # Use id() as cache key since impl instances are Python objects
        cache_key = id(impl_instance)

        # Check cache first
        if cache_key in cls._instance_cache:
            return cls._instance_cache[cache_key]

        # Create new wrapper using __new__ to bypass __init__
        wrapper = cls.__new__(cls)
        wrapper._impl_instance = impl_instance

        # Cache it
        cls._instance_cache[cache_key] = wrapper

        return wrapper

    # Generated properties
    @property
    def a(self) -> str:
        return self._impl_instance.a

    @a.setter
    def a(self, value: str):
        self._impl_instance.a = value

    @wrapped_method(Bar_moo)
    def moo(self, s: str) -> typing.Generator[str, None, None]:
        # Dummy method for type checkers and IDE navigation
        # Actual implementation is in Bar_moo.__call__
        return self.moo(s)


class _foo:
    def __call__(
        self,
    ) -> typing.Generator[int, None, None]:
        impl_function = _my_library.foo
        gen = impl_function()
        yield from get_synchronizer("my_library")._run_generator_sync(gen)

    async def aio(
        self,
    ) -> typing.AsyncGenerator[int, None]:
        impl_function = _my_library.foo
        gen = impl_function()
        async for item in get_synchronizer("my_library")._run_generator_async(gen):
            yield item


_foo_instance = _foo()


@replace_with(_foo_instance)
def foo() -> typing.Generator[int, None, None]:
    # Dummy function for type checkers and IDE navigation
    # Actual implementation is in _foo.__call__
    return _foo_instance()


class _accepts_bar:
    def __call__(self, b: Bar) -> "Bar":
        impl_function = _my_library.accepts_bar
        b_impl = b._impl_instance
        result = get_synchronizer("my_library")._run_function_sync(impl_function(b_impl))
        return Bar._from_impl(result)

    async def aio(self, b: Bar) -> "Bar":
        impl_function = _my_library.accepts_bar
        b_impl = b._impl_instance
        result = await get_synchronizer("my_library")._run_function_async(impl_function(b_impl))
        return Bar._from_impl(result)


_accepts_bar_instance = _accepts_bar()


@replace_with(_accepts_bar_instance)
def accepts_bar(b: Bar) -> "Bar":
    # Dummy function for type checkers and IDE navigation
    # Actual implementation is in _accepts_bar.__call__
    return _accepts_bar_instance(b)


def accepts_bar_sync(b: Bar) -> "Bar":
    impl_function = _my_library.accepts_bar_sync
    b_impl = b._impl_instance
    result = impl_function(b_impl)
    return Bar._from_impl(result)


class _crazy:
    def __call__(self, i: int) -> typing.Generator[str, None, None]:
        impl_function = _my_library.crazy
        gen = impl_function(i)
        yield from get_synchronizer("my_library")._run_generator_sync(gen)

    async def aio(self, i: int) -> typing.AsyncGenerator[str, None]:
        impl_function = _my_library.crazy
        gen = impl_function(i)
        async for item in get_synchronizer("my_library")._run_generator_async(gen):
            yield item


_crazy_instance = _crazy()


@replace_with(_crazy_instance)
def crazy(i: int) -> typing.Generator[str, None, None]:
    # Dummy function for type checkers and IDE navigation
    # Actual implementation is in _crazy.__call__
    return _crazy_instance(i)
