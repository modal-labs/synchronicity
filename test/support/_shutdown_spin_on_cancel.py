import asyncio
import signal

from synchronicity import Synchronizer


async def run():
    try:
        while True:
            print("running")
            await asyncio.sleep(0.3)
    except asyncio.CancelledError:
        # If wait on the cancel to finish, the main thread will hang
        while True:
            await asyncio.sleep(2)
            print("we should never print this message")
    finally:
        await asyncio.sleep(0.1)
        print("exit async")


def throw(_, __):
    raise SystemExit


if __name__ == "__main__":
    signal.signal(signal.SIGINT, throw)

    s = Synchronizer()
    blocking_run = s.create_blocking(run)
    try:
        blocking_run()
    except SystemExit:
        print("system exit")
