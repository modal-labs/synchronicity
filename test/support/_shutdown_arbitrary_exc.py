import asyncio
import signal

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


class FancyBaseException(BaseException):
    message: str


def throw(_, __):
    exc = FancyBaseException()
    exc.message = "hello"
    raise exc


if __name__ == "__main__":
    signal.signal(signal.SIGINT, throw)

    s = Synchronizer()
    blocking_run = s.create_blocking(run)
    try:
        blocking_run()
    except FancyBaseException as exc:
        assert exc.message == "hello"
        print("arbitrary base exception")
