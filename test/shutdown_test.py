import os
import pytest
import signal
import subprocess
import sys


def test_shutdown():
    # We run it in a separate process so we can simulate interrupting it
    fn = os.path.join(os.path.dirname(__file__), "_shutdown.py")
    p = subprocess.Popen(
        [sys.executable, fn],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PYTHONUNBUFFERED": "1"},
    )
    for i in range(3):  # this number doesn't matter, it's a while loop
        assert p.stdout.readline() == b"running\n"
    p.send_signal(signal.SIGINT)
    assert p.stdout.readline() == b"cancelled\n"
    assert p.stdout.readline() == b"handled cancellation\n"
    assert p.stdout.readline() == b"exit async\n"
    assert (
        p.stdout.readline() == b"keyboard interrupt\n"
    )  # we want the keyboard interrupt to come *after* the running function has been cancelled!

    stderr_content = p.stderr.read()
    assert b"Traceback" not in stderr_content


def test_keyboard_interrupt_doesnt_cancel(synchronizer):
    @synchronizer.create_blocking
    async def a():
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        a()
