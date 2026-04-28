import typing

import descriptor_dunder
from typing_extensions import assert_type

payload = descriptor_dunder.Payload(3)
descriptor = descriptor_dunder.Descriptor(payload)


class Holder:
    attr = descriptor


assert_type(Holder.attr, typing.Any)
assert_type(Holder().attr, typing.Any)
