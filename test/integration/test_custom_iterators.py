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


@pytest.mark.usefixtures("generated_wrappers")
def test_pyright_type_safety(support_files):
    check_pyright([support_files / "custom_iterators_typecheck.py"])
