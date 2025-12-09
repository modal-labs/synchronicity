from synchronicity import Synchronizer
from synchronicity.async_utils import Runner


async def blocks_event_loop():
    import time

    time.sleep(0.5)


s = Synchronizer()


@s.wrap
async def my_custom_coro_name():
    await blocks_event_loop()


with Runner() as runner:
    runner.run(my_custom_coro_name.aio())
