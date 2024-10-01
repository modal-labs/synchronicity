import os
from pathlib import Path
import pytest
import signal
import subprocess
import sys


def test_shutdown():
    # We run it in a separate process so we can simulate interrupting it
    fn = Path(__file__).parent / "support" / "_shutdown.py"
    p = subprocess.Popen(
        [sys.executable, fn],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PYTHONUNBUFFERED": "1"},
    )
    for i in range(2):  # this number doesn't matter, it's a while loop
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


def test_keyboard_interrupt_reraised_as_is(synchronizer):
    @synchronizer.create_blocking
    async def a():
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        a()


def test_shutdown_during_ctx_mgr_setup():
    # We run it in a separate process so we can simulate interrupting it
    fn = Path(__file__).parent / "support" / "_shutdown_ctx_mgr.py"
    p = subprocess.Popen(
        [sys.executable, fn, "enter"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PYTHONUNBUFFERED": "1"},
    )
    for i in range(2):  # this number doesn't matter, it's a while loop
        assert p.stdout.readline() == b"enter\n"
    p.send_signal(signal.SIGINT)
    assert p.stdout.readline() == b"exit\n"
    assert (
        p.stdout.readline() == b"keyboard interrupt\n"
    )
    assert p.stderr.read() == b""

def test_shutdown_during_ctx_mgr_yield():
    # We run it in a separate process so we can simulate interrupting it
    fn = Path(__file__).parent / "support" / "_shutdown_ctx_mgr.py"
    p = subprocess.Popen(
        [sys.executable, fn, "yield"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PYTHONUNBUFFERED": "1"},
    )
    for i in range(2):  # this number doesn't matter, it's a while loop
        assert p.stdout.readline() == b"in ctx\n"
    p.send_signal(signal.SIGINT)
    assert p.stdout.readline() == b"exit\n"
    assert (
        p.stdout.readline() == b"keyboard interrupt\n"
    )
    assert p.stderr.read() == b""
