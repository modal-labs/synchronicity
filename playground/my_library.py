import typing
import weakref

import _my_library

from synchronicity.descriptor import replace_with, wrapped_method
from synchronicity.synchronizer import get_synchronizer


class Bar_moo:
    def __init__(self, wrapper_instance):
        self._wrapper_instance = wrapper_instance

    @staticmethod
    async def _wrap_async_gen_str(_gen):
        async for _item in get_synchronizer("blah")._run_generator_async(_gen):
            yield _item

    @staticmethod
    def _wrap_async_gen_str_sync(_gen):
        for _item in get_synchronizer("blah")._run_generator_sync(_gen):
            yield _item

    def __call__(self, s: str) -> "typing.Generator[str, None, None]":
        impl_method = _my_library.Bar.moo
        gen = impl_method(self._wrapper_instance._impl_instance, s)
        yield from self._wrap_async_gen_str_sync(gen)

    async def aio(self, s: str) -> "typing.AsyncGenerator[str, None]":
        impl_method = _my_library.Bar.moo
        gen = impl_method(self._wrapper_instance._impl_instance, s)
        async for _item in self._wrap_async_gen_str(gen):
            yield _item


class Bar:
    """Wrapper class for _my_library.Bar with sync/async method support"""

    _synchronizer = get_synchronizer("blah")
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
    def moo(self, s: str) -> "typing.Generator[str, None, None]":
        # Dummy method for type checkers and IDE navigation
        # Actual implementation is in Bar_moo.__call__
        return self.moo(s)


def accepts_bar_sync(b: Bar) -> "Bar":
    impl_function = _my_library.accepts_bar_sync
    b_impl = b._impl_instance
    result = impl_function(b_impl)
    return Bar._from_impl(result)


class _foo:
    @staticmethod
    async def _wrap_async_gen_int(_gen):
        async for _item in get_synchronizer("blah")._run_generator_async(_gen):
            yield _item

    @staticmethod
    def _wrap_async_gen_int_sync(_gen):
        for _item in get_synchronizer("blah")._run_generator_sync(_gen):
            yield _item

    def __call__(
        self,
    ) -> "typing.Generator[int, None, None]":
        impl_function = _my_library.foo
        gen = impl_function()
        yield from self._wrap_async_gen_int_sync(gen)

    async def aio(
        self,
    ) -> "typing.AsyncGenerator[int, None]":
        impl_function = _my_library.foo
        gen = impl_function()
        async for _item in self._wrap_async_gen_int(gen):
            yield _item


_foo_instance = _foo()


@replace_with(_foo_instance)
def foo() -> "typing.Generator[int, None, None]":
    # Dummy function for type checkers and IDE navigation
    # Actual implementation is in _foo.__call__
    return _foo_instance()


class _accepts_bar:
    def __call__(self, b: Bar) -> "Bar":
        impl_function = _my_library.accepts_bar
        b_impl = b._impl_instance
        result = get_synchronizer("blah")._run_function_sync(impl_function(b_impl))
        return Bar._from_impl(result)

    async def aio(self, b: Bar) -> "Bar":
        impl_function = _my_library.accepts_bar
        b_impl = b._impl_instance
        result = await get_synchronizer("blah")._run_function_async(impl_function(b_impl))
        return Bar._from_impl(result)


_accepts_bar_instance = _accepts_bar()


@replace_with(_accepts_bar_instance)
def accepts_bar(b: Bar) -> "Bar":
    # Dummy function for type checkers and IDE navigation
    # Actual implementation is in _accepts_bar.__call__
    return _accepts_bar_instance(b)


class _nested_async_generator:
    @staticmethod
    async def _wrap_async_gen_str(_gen):
        async for _item in get_synchronizer("blah")._run_generator_async(_gen):
            yield _item

    @staticmethod
    def _wrap_async_gen_str_sync(_gen):
        for _item in get_synchronizer("blah")._run_generator_sync(_gen):
            yield _item

    def __call__(self, i: int) -> "tuple[typing.AsyncGenerator[str, None], ...]":
        impl_function = _my_library.nested_async_generator
        result = get_synchronizer("blah")._run_function_sync(impl_function(i))
        return tuple(self._wrap_async_gen_str(x) for x in result)

    async def aio(self, i: int) -> "tuple[typing.AsyncGenerator[str, None], ...]":
        impl_function = _my_library.nested_async_generator
        result = await get_synchronizer("blah")._run_function_async(impl_function(i))
        return tuple(self._wrap_async_gen_str(x) for x in result)


_nested_async_generator_instance = _nested_async_generator()


@replace_with(_nested_async_generator_instance)
def nested_async_generator(i: int) -> "tuple[typing.AsyncGenerator[str, None], ...]":
    # Dummy function for type checkers and IDE navigation
    # Actual implementation is in _nested_async_generator.__call__
    return _nested_async_generator_instance(i)
