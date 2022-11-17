import asyncio
import concurrent.futures

from synchronicity import Synchronizer


def test_start_loop():
    # Make sure there's no race condition in _start_loop
    s = Synchronizer()

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        ret = list(executor.map(lambda i: s._start_loop(), range(1000)))

    assert len(set(ret)) == 1
    assert isinstance(ret[0], asyncio.AbstractEventLoop)
