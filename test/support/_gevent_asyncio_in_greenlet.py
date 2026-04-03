"""
Support script for test_gevent_asyncio_in_greenlet.

Demonstrates the bug: when gevent is active and an asyncio event loop is running
in one greenlet, calling synchronicity blocking functions from another greenlet
fails because gevent makes asyncio._get_running_loop() visible globally.
"""

import sys

import gevent.monkey

gevent.monkey.patch_all()

import asyncio  # noqa: E402

import gevent  # noqa: E402

import synchronicity  # noqa: E402

synchronicity.patch_asyncio_for_gevent()
syn = synchronicity.Synchronizer()


async def afunc(x):
    await asyncio.sleep(0.01)
    return x * 2


blocking_func = syn.create_blocking(afunc)


def run_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(asyncio.sleep(0.2))
    finally:
        loop.close()


def run_blocking():
    try:
        result = blocking_func(5)
        assert result == 10, f"Expected 10, got {result}"
        return None
    except Exception as e:
        return e


if __name__ == "__main__":
    loop_greenlet = gevent.spawn(run_loop)
    # Give the loop greenlet a moment to start its event loop
    gevent.sleep(0.05)

    blocking_greenlet = gevent.spawn(run_blocking)
    blocking_greenlet.join()
    loop_greenlet.join()

    err = blocking_greenlet.value
    if err is not None:
        print(f"ERROR: {type(err).__name__}: {err}", file=sys.stderr)
        sys.exit(1)

    print("SUCCESS")
    sys.exit(0)
