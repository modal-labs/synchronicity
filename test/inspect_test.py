import inspect

from synchronicity import Synchronizer


class _Api:
    def blocking_func(self):
        pass

    async def async_func(self):
        pass


def test_inspect_coroutinefunction():
    s = Synchronizer()
    BlockingApi = s.create_blocking(_Api)
    AioApi = s.create_async(_Api)

    assert inspect.iscoroutinefunction(BlockingApi.blocking_func) is False
    assert inspect.iscoroutinefunction(BlockingApi.async_func) is False
    assert inspect.iscoroutinefunction(AioApi.blocking_func) is False
    assert inspect.iscoroutinefunction(AioApi.async_func) is True
