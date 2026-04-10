import pytest

from synchronicity.synchronizer import Synchronizer


def test_resolve_wrapper_class_requires_wrapper_location():
    class Impl:
        pass

    sync = Synchronizer("test_synchronizer_missing_wrapper_location")

    with pytest.raises(RuntimeError, match="has no registered wrapper location"):
        sync._resolve_wrapper_class(Impl())
