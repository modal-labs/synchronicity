import pytest
import subprocess
import sys
from pathlib import Path


@pytest.mark.skipif(sys.platform == "win32", reason="Windows can't fork")
def test_fork_restarts_loop():
    with subprocess.Popen(
        [sys.executable, Path(__file__).parent / "support" / "_forker.py"],
        encoding="utf8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as p:
        try:
            stdout, stderr = p.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            p.kill()
            assert False, "Fork process hanged"

        assert p.returncode == 0
        assert stdout == "done\ndone\n"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows can't fork")
def test_fork_during_start_loop_no_deadlock():
    """Forking while _loop_creation_lock is held must not deadlock the child.

    Regression test for a bug where threading.Lock was inherited in a locked
    state after os.fork(), causing _start_loop() to deadlock permanently.
    """
    with subprocess.Popen(
        [sys.executable, Path(__file__).parent / "support" / "_fork_lock_test.py"],
        encoding="utf8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as p:
        try:
            stdout, stderr = p.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            p.kill()
            assert False, "Fork lock test timed out (likely deadlocked)"

        assert p.returncode == 0, f"Fork lock test failed:\nstdout: {stdout}\nstderr: {stderr}"
        assert "PASS" in stdout
