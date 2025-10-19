import asyncio

import synchronicity

s = synchronicity.Synchronizer()


@s.wrap
async def f():
    async with asyncio.timeout(0.01):
        await asyncio.sleep(1)
        raise Exception("asdf")


f()
