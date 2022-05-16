import subprocess
import os
import pytest
import signal
import sys


@pytest.mark.timeout(5)
def test_shutdown():
    # We run it in a separate process so we can simulate interrupting it
    fn = os.path.join(os.path.dirname(__file__), "_shutdown.py")
    p = subprocess.Popen(
        [sys.executable, fn],
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        env={"PYTHONUNBUFFERED": "1"},
    )
    for i in range(7):  # this number doesn't matter, it's a while loop
        assert p.stdout.readline() == b"running\n"
    p.send_signal(signal.SIGINT)
    assert p.stdout.readline() == b"stopping\n"
    assert p.stdout.readline() == b"exiting\n"
