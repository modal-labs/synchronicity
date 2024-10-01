import subprocess
import sys
from pathlib import Path


def test_gevent():
    # Run it in a separate process because gevent modifies a lot of modules
    fn = Path(__file__).parent / "support" / "_gevent.py"
    ret = subprocess.run([sys.executable, fn], stdout=sys.stdout, stderr=sys.stderr, timeout=5)
    assert ret.returncode == 0
