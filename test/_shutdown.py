import asyncio
from synchronicity import Synchronizer

async def run():
    try:
        while True:
            print("running")
            await asyncio.sleep(0.1)
    finally:
        print("stopping")
        await asyncio.sleep(0.1)
        print("exiting")


s = Synchronizer()
s(run)()
