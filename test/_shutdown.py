import asyncio
from synchronicity import Synchronizer


async def run():
    try:
        while True:
            print("running")
            await asyncio.sleep(0.3)
    except asyncio.CancelledError:
        print("cancelled")
        raise
    finally:
        print("stopping")
        await asyncio.sleep(0.1)
        print("exiting")


s = Synchronizer()

try:
    s.create_blocking(run)()
except KeyboardInterrupt:
    pass
