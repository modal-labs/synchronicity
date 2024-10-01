import os

import synchronicity

synchronizer = synchronicity.Synchronizer()


@synchronizer.create_blocking
async def dummy():
    print("done", flush=True)


if __name__ == "__main__":
    dummy()  # this starts a synchronizer loop/thread
    if not os.fork():
        assert not synchronizer._thread.is_alive()  # threads don't come along in forks
        dummy()  # this should still work
