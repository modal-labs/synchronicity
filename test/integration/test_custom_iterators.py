import pytest

from .test_utils import check_pyright


@pytest.mark.usefixtures("generated_wrappers")
def test_usage_sync():
    import custom_iterators

    for i in custom_iterators.get_iterator():
        print(i)

    for i in custom_iterators.get_iterable():
        print(i)

    iterable_instance = custom_iterators.CustomAsyncIterable()
    for i in iterable_instance:
        print(i)

    instance2 = custom_iterators.IterableClassUsingGenerator()
    for i in instance2:
        print(i)


@pytest.mark.usefixtures("generated_wrappers")
@pytest.mark.asyncio
async def test_usage_async():
    import custom_iterators

    async for i in custom_iterators.get_iterator():
        print(i)

    async for i in custom_iterators.get_iterable():
        print(i)

    iterable_instance = custom_iterators.CustomAsyncIterable()
    async for i in iterable_instance:
        print(i)

    instance2 = custom_iterators.IterableClassUsingGenerator()
    async for i in instance2:
        print(i)

    instance3 = custom_iterators.IterableClassUsingGeneratorTyped()
    async for i in instance3:
        print(i)


@pytest.mark.usefixtures("generated_wrappers")
def test_pyright_type_safety(support_files):
    # TODO: add Path(custom_iterators.__file__) to check
    check_pyright([support_files / "custom_iterators_typecheck.py"])
