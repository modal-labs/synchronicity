"""Test that forking while _loop_creation_lock is held does not deadlock the child.

This reproduces a bug where threading.Lock (_loop_creation_lock) was inherited
in a locked state after os.fork(), causing _start_loop() to deadlock in the child.
"""

import multiprocessing
import os
import threading

import synchronicity


def main():
    multiprocessing.set_start_method("fork")

    syn = synchronicity.Synchronizer()

    @syn.create_blocking
    async def hello():
        return f"hello from pid={os.getpid()}"

    # Start the loop in the parent
    hello()

    hangs = 0
    total = 30

    for _ in range(total):
        syn._close_loop()

        # Start _start_loop in a background thread — this acquires _loop_creation_lock
        started = threading.Event()

        def bg():
            started.set()
            syn._start_loop()

        t = threading.Thread(target=bg, daemon=True)
        t.start()
        started.wait()

        # Fork while _start_loop might hold the lock
        rq = multiprocessing.Queue()

        def child(rq):
            try:
                rq.put(hello())
            except Exception as e:
                rq.put(f"error: {e}")

        p = multiprocessing.Process(target=child, args=(rq,))
        p.start()
        p.join(timeout=5)

        if p.is_alive():
            hangs += 1
            p.kill()
            p.join()

        t.join(timeout=2)

    if hangs > 0:
        print(f"FAIL: {hangs}/{total} children deadlocked", flush=True)
        raise SystemExit(1)
    else:
        print(f"PASS: 0/{total} deadlocks", flush=True)


if __name__ == "__main__":
    main()
