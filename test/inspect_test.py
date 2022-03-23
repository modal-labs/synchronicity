import inspect

from synchronicity import Synchronizer, Interface


class _Api:
    def blocking_func(self):
        pass

    async def async_func(self):
        pass


def test_inspect_coroutinefunction():
    s = Synchronizer()
    interfaces = s.create(_Api)

    BlockingApi = interfaces[Interface.BLOCKING]
    AioApi = interfaces[Interface.ASYNC]

    assert inspect.iscoroutinefunction(BlockingApi.blocking_func) == False
    assert inspect.iscoroutinefunction(BlockingApi.async_func) == False
    assert inspect.iscoroutinefunction(AioApi.blocking_func) == False
    assert inspect.iscoroutinefunction(AioApi.async_func) == True
