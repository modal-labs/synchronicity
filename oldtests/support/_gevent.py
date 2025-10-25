from gevent import monkey

monkey.patch_all()

import asyncio  # noqa: E402

from synchronicity import Synchronizer  # noqa: E402


async def f(x):
    await asyncio.sleep(0.1)
    return x**2


s = Synchronizer()
f_s = s.create_blocking(f)
for i in range(3):
    assert f_s(42) == 1764
