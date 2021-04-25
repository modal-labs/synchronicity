import pickle
from synchronicity import Synchronizer


s = Synchronizer()

@s
class PicklableClass:
    async def f(self, x):
        return x**2


def test_pickle():
    obj = PicklableClass()
    assert obj.f(42) == 1764
    pickle.dumps(obj)
