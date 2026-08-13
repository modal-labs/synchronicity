def test_is_synchronized(synchronizer):
    class Foo:
        pass

    BlockingFoo = synchronizer.create_blocking(Foo)
    assert synchronizer.is_synchronized(Foo) is False
    assert synchronizer.is_synchronized(BlockingFoo) is True


def test_generated_wrapper_interoperability(synchronizer):
    class Foo:
        pass

    BlockingFoo = synchronizer.wrap(Foo, name="Foo", target_module="example.foo")
    wrapped = BlockingFoo()
    impl = synchronizer._translate_in(wrapped)

    assert synchronizer._translate_out(Foo) is BlockingFoo
    assert synchronizer._translate_out(impl) is wrapped
    assert not hasattr(wrapped, "_impl_instance")

    class GeneratedSubclass(BlockingFoo):
        pass

    assert issubclass(GeneratedSubclass, BlockingFoo)

    class ExternalFoo(Foo):
        pass

    class ExternalFooWrapper(BlockingFoo):
        pass

    synchronizer.register_external_wrapper_class(ExternalFoo, ExternalFooWrapper)
    external_impl = ExternalFoo()
    external_wrapper = ExternalFooWrapper.__new__(ExternalFooWrapper)
    synchronizer.register_external_wrapper_instance(external_impl, external_wrapper)

    assert not hasattr(external_wrapper, "_impl_instance")
    assert synchronizer._translate_in(external_wrapper) is external_impl
    assert synchronizer._translate_out(external_impl) is external_wrapper


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
