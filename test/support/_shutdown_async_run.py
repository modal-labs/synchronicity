import asyncio

from synchronicity import Synchronizer
from synchronicity.async_utils import Runner


async def run():
    try:
        while True:
            await asyncio.sleep(0.2)
            print("running")

    except asyncio.CancelledError:
        print("cancelled")
        await asyncio.sleep(0.1)
        print("handled cancellation")
        raise
    finally:
        await asyncio.sleep(0.1)
        print("exit async")


s = Synchronizer()

blocking_run = s.create_blocking(run)


try:
    with Runner() as runner:
        runner.run(blocking_run.aio())
except KeyboardInterrupt:
    print("keyboard interrupt")
