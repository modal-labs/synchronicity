import asyncio
import contextlib
import time

from synchronicity import Synchronizer

s = Synchronizer()


async def _f():
    pass


f = s.wrap(_f)


@contextlib.contextmanager
def timer(test_str: str):
    t0 = time.monotonic()
    yield
    t1 = time.monotonic()
    print(f"Ran {test_str} in {t1 - t0} seconds")


n = 10_000


async def run_original():
    with timer(f"original * {n}"):
        [(await _f()) for i in range(n)]


asyncio.run(run_original())

with timer(f"sync * {n}"):
    [f() for i in range(n)]


async def run_some_async():
    with timer(f"async * {n}"):
        [(await f.aio()) for i in range(n)]


asyncio.run(run_some_async())
