import pytest
import subprocess
import sys
from pathlib import Path


@pytest.mark.skipif(sys.version_info >= (3, 13), reason="gevent seems broken on Python 3.13")
@pytest.mark.skipif(
    sys.platform == "win32", reason="gevent support broken on Windows, probably due to event loop patching"
)
def test_gevent():
    # Run it in a separate process because gevent modifies a lot of modules
    fn = Path(__file__).parent / "support" / "_gevent.py"
    ret = subprocess.run([sys.executable, fn], stdout=sys.stdout, stderr=sys.stderr, timeout=5)
    assert ret.returncode == 0
