import subprocess
import os
import signal
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
    assert p.stdout.readline() == b"stopping\n"
    assert p.stdout.readline() == b"exiting\n"
    stderr_content = p.stderr.read()
    assert b"Traceback" not in stderr_content
