"""Type checking test file for asynchronous multifile usage."""

from typing import reveal_type

from multifile.a import A, get_b
from multifile.b import B, get_a


async def test():
    # Async usage - classes are instantiated normally, methods have .aio
    reveal_type(A)
    reveal_type(B)
    reveal_type(get_a.aio)
    reveal_type(get_b.aio)

    a = A(value=42)
    reveal_type(a)
    reveal_type(a.get_value.aio)

    val = await a.get_value.aio()
    reveal_type(val)

    b = await get_b.aio()
    reveal_type(b)

    a2 = await get_a.aio()
    reveal_type(a2)
