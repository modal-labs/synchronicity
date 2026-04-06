import pytest
import sys

from synchronicity import Synchronizer


@pytest.fixture(autouse=True)
def use_asyncio_debug(monkeypatch, request):
    if sys.platform == "win32" and request.node.get_closest_marker("disable_asyncio_debug_on_windows"):
        monkeypatch.delenv("PYTHONASYNCIODEBUG", raising=False)
    else:
        monkeypatch.setenv("PYTHONASYNCIODEBUG", "1")


@pytest.fixture()
def synchronizer(use_asyncio_debug):
    s = Synchronizer()
    yield s
    s._close_loop()  # avoid "unclosed event loop" warnings in tests when garbage collecting synchronizers
