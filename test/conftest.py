import pytest

from synchronicity import Synchronizer


@pytest.fixture(autouse=True)
def use_asyncio_debug(monkeypatch):
    monkeypatch.setenv("PYTHONASYNCIODEBUG", "1")


@pytest.fixture()
def synchronizer(use_asyncio_debug):
    s = Synchronizer()
    yield s
    s._close_loop()  # avoid "unclosed event loop" warnings in tests when garbage collecting synchronizers
