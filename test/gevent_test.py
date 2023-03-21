import subprocess
import os
import sys


def test_gevent():
    # Run it in a separate process because gevent modifies a lot of modules
    fn = os.path.join(os.path.dirname(__file__), "_gevent.py")
    ret = subprocess.run(
        [sys.executable, fn], stdout=sys.stdout, stderr=sys.stderr, timeout=5
    )
    assert ret.returncode == 0
