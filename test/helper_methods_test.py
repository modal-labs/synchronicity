def test_is_synchronized(synchronizer):
    class Foo:
        pass

    BlockingFoo = synchronizer.create_blocking(Foo)
    assert synchronizer.is_synchronized(Foo) is False
    assert synchronizer.is_synchronized(BlockingFoo) is True


def test_external_wrapper_interoperability(synchronizer):
    class Foo:
        pass

    BlockingFoo = synchronizer.wrap(Foo, name="Foo", target_module="example.foo")
    assert synchronizer._translate_out(Foo) is BlockingFoo

    wrapped = BlockingFoo()
    impl = synchronizer._translate_in(wrapped)
    assert synchronizer._translate_out(impl) is wrapped

    class ExternalSubclass(BlockingFoo):
        pass

    assert issubclass(ExternalSubclass, BlockingFoo)

    class ExternalFoo:
        pass

    class ExternalFooWrapper:
        _cache = {}

        @classmethod
        def _from_impl(cls, impl):
            wrapper = cls._cache.get(id(impl))
            if wrapper is None:
                wrapper = cls.__new__(cls)
                wrapper._impl_instance = impl
                cls._cache[id(impl)] = wrapper
            return wrapper

    synchronizer.register_external_wrapper_class(
        ExternalFoo,
        ExternalFooWrapper,
        translate_in=lambda wrapper: wrapper._impl_instance,
        translate_out=ExternalFooWrapper._from_impl,
    )
    external_impl = ExternalFoo()
    external_wrapper = synchronizer._translate_out(external_impl)

    @synchronizer.wrap
    async def echo_external(value):
        assert value is external_impl
        return value

    assert external_wrapper._impl_instance is external_impl
    assert synchronizer._translate_out(ExternalFoo) is ExternalFooWrapper
    assert synchronizer._translate_in(ExternalFooWrapper) is ExternalFoo
    assert synchronizer._translate_in(external_wrapper) is external_impl
    assert synchronizer._translate_out(external_impl) is external_wrapper
    assert echo_external(external_wrapper) is external_wrapper
    assert synchronizer._translate_out([external_impl]) == [external_wrapper]
    assert synchronizer._translate_in({"value": external_wrapper}) == {"value": external_impl}


def test_wrapping_subclass_does_not_run_implementation_init_subclass(synchronizer):
    implementation_subclasses = []

    class Foo:
        @classmethod
        def __init_subclass__(cls):
            super().__init_subclass__()
            implementation_subclasses.append(cls)

    class FooImplSubclass(Foo):
        pass

    assert implementation_subclasses == [FooImplSubclass]

    implementation_subclasses.clear()

    BlockingFooImplSubclass = synchronizer.wrap(FooImplSubclass)

    assert synchronizer._translate_out(FooImplSubclass) is BlockingFooImplSubclass
    assert implementation_subclasses == []
