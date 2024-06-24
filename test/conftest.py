import pytest

from synchronicity import Synchronizer


@pytest.fixture()
def synchronizer():
    s = Synchronizer()
    yield s
    s._close_loop()  # avoid "unclosed event loop" warnings in tests when garbage collecting synchronizers
