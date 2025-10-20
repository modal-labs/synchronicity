from typing import reveal_type
from my_library import Bar, accepts_bar

b = Bar("hello")
reveal_type(b)
b2 = accepts_bar(b)
reveal_type(accepts_bar.__call__)
reveal_type(accepts_bar.aio)
assert b2._impl_instance is b._impl_instance
assert b2 is b


import modal


app = modal.App()

app.run