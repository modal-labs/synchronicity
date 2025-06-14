import pytest

from synchronicity import Synchronizer


@pytest.fixture()
def synchronizer(request):
    s = Synchronizer()
    orig_get_loop = s._get_loop

    def custom_repr(self):
        return request.node.name

    def get_loop(self, start=False):
        loop = orig_get_loop(start)
        if loop:
            loop.get_debug = custom_repr.__get__(loop)  # haxx
        return loop

    s._get_loop = get_loop.__get__(s)

    yield s
    print("closing synchronizer for test", request.node.name)
    s._close_loop()  # avoid "unclosed event loop" warnings in tests when garbage collecting synchronizers


@pytest.fixture(autouse=True)
def nowarns(recwarn):
    yield
    assert len(recwarn) == 0
