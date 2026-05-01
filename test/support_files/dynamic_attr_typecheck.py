import typing

import dynamic_attr
from typing_extensions import assert_type

owner = dynamic_attr.DynamicOwner(dynamic_attr.Payload(7))

assert_type(owner.payload, typing.Any)
assert_type(owner.count, typing.Any)
