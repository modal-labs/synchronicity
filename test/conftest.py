import pytest

from synchronicity import Synchronizer


@pytest.fixture()
def synchronizer(request):
    s = Synchronizer()
    loop = s._get_loop(start=True)

    def custom_repr(self):
        return request.node.name

    loop.get_debug = custom_repr.__get__(loop)  # haxx
    yield s
    print("closing synchronizer for test", request.node.name)
    s._close_loop()  # avoid "unclosed event loop" warnings in tests when garbage collecting synchronizers
