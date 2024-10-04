import asyncio

from synchronicity import Synchronizer


async def run():
    try:
        while True:
            print("running")
            await asyncio.sleep(0.3)
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
    asyncio.run(blocking_run.aio())
except KeyboardInterrupt:
    print("keyboard interrupt")
