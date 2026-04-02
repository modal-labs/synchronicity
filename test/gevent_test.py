import pytest
import subprocess
import sys
from pathlib import Path

pytest.importorskip("gevent")


@pytest.mark.skipif(sys.version_info >= (3, 13), reason="gevent seems broken on Python 3.13")
@pytest.mark.skipif(
    sys.platform == "win32", reason="gevent support broken on Windows, probably due to event loop patching"
)
def test_gevent():
    # Run it in a separate process because gevent modifies a lot of modules
    fn = Path(__file__).parent / "support" / "_gevent.py"
    ret = subprocess.run([sys.executable, fn], stdout=sys.stdout, stderr=sys.stderr, timeout=5)
    assert ret.returncode == 0


@pytest.mark.xfail(
    strict=True,
    reason="gevent makes asyncio._get_running_loop() global, causing RuntimeError when a loop is running in another greenlet",
)
@pytest.mark.skipif(sys.version_info >= (3, 13), reason="gevent seems broken on Python 3.13")
@pytest.mark.skipif(
    sys.platform == "win32", reason="gevent support broken on Windows, probably due to event loop patching"
)
def test_gevent_asyncio_in_greenlet():
    # Run it in a separate process because gevent modifies a lot of modules
    fn = Path(__file__).parent / "support" / "_gevent_asyncio_in_greenlet.py"
    ret = subprocess.run([sys.executable, fn], stdout=sys.stdout, stderr=sys.stderr, timeout=10)
    assert ret.returncode == 0
