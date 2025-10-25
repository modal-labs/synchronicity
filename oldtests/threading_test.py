import asyncio
import concurrent.futures
import time


def test_start_loop(synchronizer):
    # Make sure there's no race condition in _start_loop
    with concurrent.futures.ThreadPoolExecutor() as executor:
        ret = list(executor.map(lambda i: synchronizer._start_loop(), range(1000)))

    assert len(set(ret)) == 1
    assert isinstance(ret[0], asyncio.AbstractEventLoop)


async def f(i):
    await asyncio.sleep(1.0)
    return i**2


def test_multithreaded(synchronizer, n_threads=20):
    f_s = synchronizer.create_blocking(f)

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as executor:
        ret = list(executor.map(f_s, range(n_threads)))
    assert 1.0 <= time.time() - t0 < 1.2
    assert ret == [i**2 for i in range(n_threads)]
