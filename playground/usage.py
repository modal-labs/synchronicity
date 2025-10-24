import asyncio
from typing import reveal_type

from my_library import Bar, accepts_bar, crazy

b = Bar("hello")
reveal_type(b)
b2 = accepts_bar(b)
reveal_type(accepts_bar.__call__)
reveal_type(accepts_bar.aio)
assert b2._impl_instance is b._impl_instance
# assert b2 is b

reveal_type(crazy.__call__)


async def main():
    async for res in crazy.aio(2):
        print(res)


asyncio.run(main())

reveal_type(crazy(i=10))
