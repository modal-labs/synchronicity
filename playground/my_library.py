import typing

import _my_library

from synchronicity2.synchronizer import get_synchronizer

NoneType = None


class _fooWrapper:
    synchronizer = get_synchronizer("my_library")
    impl_function = _my_library.foo  # reference to original function

    def __call__(
        self,
    ) -> typing.Iterator[int]:
        gen = self.impl_function()
        yield from self.synchronizer._run_generator_sync(gen)

    async def aio(
        self,
    ) -> typing.AsyncGenerator[int, NoneType]:
        gen = self.impl_function()
        async for item in self.synchronizer._run_generator_async(gen):
            yield item


foo = _fooWrapper()


class Bar_moo:
    _synchronizer = get_synchronizer("my_library")

    def __call__(self, s: str) -> typing.Iterator[bool]:
        # This is what actually gets called when doing Bar().moo(...)
        return self.sync_wrapper_method(s)

    async def aio(self, s: str) -> typing.AsyncGenerator[bool, NoneType]:
        gen = _my_library.Bar.moo(self.instance, s)
        async for item in self._synchronizer._run_generator_async(gen):
            yield item


T = typing.TypeVar("T")


class WrappedMethodDescriptor(typing.Generic[T]):
    unbound_impl_method: typing.Callable[...]
    method_wrapper_type: type[T]
    sync_wrapper_method: typing.Callable[...]

    def __init__(self, sync_wrapper_method):
        self.sync_wrapper_method = sync_wrapper_method

    def __get__(self, wrapper_instance, owner) -> T:
        if wrapper_instance is None:
            return self

        return self.method_wrapper_type(
            wrapper_instance._impl_instance, self.synchronizer, self.unbound_impl_method, self.sync_wrapper_method
        )


def wrapped_method(unbound_impl_method, method_wrapper_type: type[T]):
    def decorator(sync_wrapper_method) -> WrappedMethodDescriptor[T]:
        descriptor = WrappedMethodDescriptor(unbound_impl_method, method_wrapper_type)

        descriptor.unbound_impl_method = unbound_impl_method
        descriptor.method_wrapper_type = method_wrapper_type
        descriptor.sync_wrapper_method = sync_wrapper_method
        return descriptor

    return decorator


class Bar:
    """Wrapper class for my_library.Bar with sync/async method support"""

    _synchronizer = get_synchronizer("my_library")

    a: str

    def __init__(self, *args, **kwargs):
        self._impl_instance = _my_library.Bar(*args, **kwargs)

    @wrapped_method(_my_library.Bar.moo, Bar_moo)  # this adds the .aio variant
    def moo(self, s: str) -> typing.Iterator[str]:
        # This is where language servers will navigate when going to definition for Bar().moo
        # For that reason, we put the generated *sync* proxy implementation here with the
        # sync method signature.
        # However, this is *not* the method that gets immediately called when
        # Bar().moo() is called - that goes via the descriptor that in turn calls back to this
        # This complicated control flow is done in order to maximize code navigation usability.
        # This sync method implementation should be really short for that reason and just delegate
        # calls to the original instance + input/output translation
        gen = _my_library.Bar.moo(self._original_instance, s)
        yield from self._synchronizer._run_generator_sync(gen)


Bar().moo.aio
# d = wrapped_method(_my_library.Bar.moo, Bar_moo)
# m = d.__get__(Bar(), Bar)
# m.aio()
