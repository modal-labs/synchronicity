# this code is only meant to be "running" through mypy and not an actual python interpreter!
import typing

from typing_extensions import assert_type

from test.type_stub_helpers import e2e_example_export

blocking_foo = e2e_example_export.BlockingFoo("hello")

# assert start
assert_type(blocking_foo, e2e_example_export.BlockingFoo)

assert_type(blocking_foo.getarg(), str)
assert_type(blocking_foo.gen(), typing.Generator[int, None, None])

assert_type(e2e_example_export.some_instance, typing.Optional[e2e_example_export.BlockingFoo])

assert_type(blocking_foo.some_static("foo"), float)

assert_type(e2e_example_export.BlockingFoo.clone(blocking_foo), e2e_example_export.BlockingFoo)
assert_type(e2e_example_export.BlockingFoo.slow_clone(blocking_foo), e2e_example_export.BlockingFoo)

assert_type(blocking_foo.singleton, e2e_example_export.BlockingFoo)


assert_type(
    e2e_example_export.listify(blocking_foo),
    typing.List[e2e_example_export.BlockingFoo],
)


assert_type(e2e_example_export.overloaded("12"), float)

assert_type(e2e_example_export.overloaded(12), int)


with e2e_example_export.wrapped_make_context(10.0) as c:
    assert_type(c, str)


async def async_block() -> None:
    res = await e2e_example_export.returns_foo.aio()
    assert_type(res, e2e_example_export.BlockingFoo)

    async with e2e_example_export.wrapped_make_context(10.0) as c:
        assert_type(c, str)

    # not sure if this should actually be supported, but it is, for completeness:
    async with e2e_example_export.wrapped_make_context.aio(10.0) as c:
        assert_type(c, str)

    assert_type(e2e_example_export.BlockingFoo.slow_clone(blocking_foo), e2e_example_export.BlockingFoo)


def f(a: str) -> float:
    return 0.1


res = e2e_example_export.wrap_callable(f).func(a="q")
assert_type(res, float)


custom = e2e_example_export.SomeGeneric.custom_constructor()

assert_type(custom, e2e_example_export.SomeGeneric[str])
