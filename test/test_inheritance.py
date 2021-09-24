import asyncio

from synchronicity import Synchronizer


class Vehicle:
    async def go(self):
        await asyncio.sleep(0.1)
        return "Done"


class Car(Vehicle):
    async def drive(self):
        return await self.go()



def test_synchronize_subclass():
    s = Synchronizer()
    Car_sync = s(Car)
    car = Car_sync()

    ret = car.drive()
    assert ret == "Done"

    ret = car.go()
    assert ret == "Done"
