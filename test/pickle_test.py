import pickle
import pytest

from synchronicity import Interface, Synchronizer


class PicklableClass:
    async def f(self, x):
        return x**2


@pytest.mark.skip(reason="Let's revisit this in 0.2.0")
def test_pickle():
    s = Synchronizer()
    BlockingPicklableClass = s.create(PicklableClass, Interface.BLOCKING)
    obj = BlockingPicklableClass()
    assert obj.f(42) == 1764
    data = pickle.dumps(obj)
    obj2 = pickle.loads(data)
    assert obj2.f(43) == 1849


def test_pickle_synchronizer():
    s = Synchronizer()
    pickle.dumps(s)
