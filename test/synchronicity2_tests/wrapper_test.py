import asyncio
import pytest

from synchronicity2.synchronizer import get_synchronizer
from synchronicity2.wrappers import GenericFunctionWrapper


@pytest.mark.asyncio
async def test_generic_function_wrapper_async_and_sync():
    # This will store the event loop used by the coroutine
    loop_ids = []

    async def my_coro(x):
        loop_ids.append(id(asyncio.get_running_loop()))
        await asyncio.sleep(0.01)
        return x * 2

    synchronizer = get_synchronizer("test_generic_function_wrapper")
    wrapper = GenericFunctionWrapper(my_coro, synchronizer)

    # Call synchronously
    result_sync = wrapper(21)
    assert result_sync == 42
    assert len(loop_ids) == 1

    # Call asynchronously
    result_async = await wrapper.aio(10)
    assert result_async == 20
    assert len(loop_ids) == 2

    # Both calls should have used the same event loop (the synchronizer's loop)
    assert loop_ids[0] == loop_ids[1]

    # Call again to check that the event loop remains the same
    result_sync2 = wrapper(5)
    assert result_sync2 == 10
    assert len(loop_ids) == 3
    assert loop_ids[2] == loop_ids[0]


@pytest.mark.asyncio
async def test_generic_function_wrapper_multiple_wrappers_same_loop():
    # This test checks that two wrappers using the same synchronizer share the same event loop

    loop_ids = []

    async def coro1():
        loop_ids.append(id(asyncio.get_running_loop()))
        return "a"

    async def coro2():
        loop_ids.append(id(asyncio.get_running_loop()))
        return "b"

    synchronizer = get_synchronizer("test_generic_function_wrapper_multi")
    wrapper1 = GenericFunctionWrapper(coro1, synchronizer)
    wrapper2 = GenericFunctionWrapper(coro2, synchronizer)

    # Call both synchronously
    assert wrapper1() == "a"
    assert wrapper2() == "b"
    # Call both asynchronously
    assert await wrapper1.aio() == "a"
    assert await wrapper2.aio() == "b"

    # All calls should have used the same event loop
    assert len(loop_ids) == 4
    assert all(lid == loop_ids[0] for lid in loop_ids)
