import asyncio

from synchronicity import Synchronizer


class DummyConnection:
    async def run_query(self, query):
        pass


async def dummy_connect_to_db(url):
    return DummyConnection()


def pytest_markdown_docs_globals():
    synchronizer = Synchronizer()
    return {
        "synchronizer": synchronizer,
        "asyncio": asyncio,
        "connect_to_database": dummy_connect_to_db,
    }
