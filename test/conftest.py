import pytest


@pytest.fixture(autouse=True)
def use_asyncio_debug(monkeypatch):
    monkeypatch.setenv("PYTHONASYNCIODEBUG", "1")
