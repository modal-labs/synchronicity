import inspect


class _Api:
    def blocking_func(self):
        pass

    async def async_func(self):
        pass


def test_inspect_coroutinefunction(synchronizer):
    BlockingApi = synchronizer.create_blocking(_Api)

    assert inspect.iscoroutinefunction(BlockingApi.blocking_func) is False
    assert inspect.iscoroutinefunction(BlockingApi.async_func) is False
    assert hasattr(BlockingApi.blocking_func, "aio") is False
    assert inspect.iscoroutinefunction(BlockingApi.async_func.aio) is True
