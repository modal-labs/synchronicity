import asyncio
import time


def test_nowrap(synchronizer):
    @synchronizer.create_blocking
    class MyClass:
        async def f(self, x):
            await asyncio.sleep(0.2)
            return x**2

        @synchronizer.nowrap
        def g(self, x):
            # This runs on the wrapped class
            return self.f(x) * x  # calls the blocking function

    my_obj = MyClass()

    t0 = time.time()
    assert my_obj.f(111) == 12321
    assert 0.15 < time.time() - t0 < 0.25

    t0 = time.time()
    assert my_obj.g(111) == 1367631
    assert 0.15 < time.time() - t0 < 0.25
