import asyncio
import pytest
import typing

from synchronicity import Synchronizer


class DummyConnection:
    async def run_query(self, query):
        pass


async def dummy_connect_to_db(url):
    return DummyConnection()


@pytest.fixture()
def quicksleep(monkeypatch):
    from asyncio import sleep as original_sleep

    monkeypatch.setattr("asyncio.sleep", lambda x: original_sleep(x / 1000.0))


def pytest_markdown_docs_globals():
    synchronizer = Synchronizer()
    return {
        "typing": typing,
        "synchronizer": synchronizer,
        "asyncio": asyncio,
        "connect_to_database": dummy_connect_to_db,
    }
