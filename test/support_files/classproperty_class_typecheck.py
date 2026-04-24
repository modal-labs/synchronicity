"""Consumer typing checks for generated classproperty_class wrappers."""

from typing import assert_type

import classproperty_class


def _sync_usage() -> None:
    assert_type(classproperty_class.Service.manager, classproperty_class.Manager)
    assert_type(classproperty_class.Service.manager.describe(), str)
    assert_type(classproperty_class.Service.default_name, str)

    service = classproperty_class.Service()
    assert_type(service.manager, classproperty_class.Manager)
    assert_type(service.default_name, str)
