import os

import synchronicity

synchronizer = synchronicity.Synchronizer()


@synchronizer.create_blocking
async def dummy():
    print("done", flush=True)


if __name__ == "__main__":
    dummy()  # this starts a synchronizer loop/thread
    if not os.fork():
        # After fork, _reinitialize_after_fork resets _thread to None
        assert synchronizer._thread is None  # reset by register_at_fork handler
        dummy()  # this should still work
