import asyncio
import time

from synchronicity import Synchronizer

SLEEP_DELAY = 0.1

s = Synchronizer()


class ObjectMetaclass(type):
    def __new__(metacls, name, bases, dct):
        new_cls = s.create_class(metacls, name, bases, dct)
        return new_cls


class ObjectBase(metaclass=ObjectMetaclass):
    async def square(self, x):
        await asyncio.sleep(SLEEP_DELAY)
        return x ** 2


class ObjectDerived(ObjectBase):
    async def cube(self, x):
        await asyncio.sleep(SLEEP_DELAY)
        return x ** 3


def test_base():
    base = ObjectBase()
    t0 = time.time()
    assert base.square(42) == 42 * 42
    assert SLEEP_DELAY <= time.time() - t0 < 2 * SLEEP_DELAY


def test_derived():
    derived = ObjectDerived()
    t0 = time.time()
    assert derived.square(42) == 42 * 42
    assert derived.cube(42) == 42 * 42 * 42
    assert 2 * SLEEP_DELAY <= time.time() - t0 < 3 * SLEEP_DELAY
