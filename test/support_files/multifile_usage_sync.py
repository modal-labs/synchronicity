"""Type checking test file for synchronous multifile usage."""

from typing import reveal_type

from multifile.a import A, get_b
from multifile.b import B, get_a

# Sync usage
reveal_type(A)
reveal_type(B)
reveal_type(get_a)
reveal_type(get_b)

a = A(value=42)
reveal_type(a)
reveal_type(a.get_value)

val = a.get_value()
reveal_type(val)

b = get_b()
reveal_type(b)

a2 = get_a()
reveal_type(a2)
