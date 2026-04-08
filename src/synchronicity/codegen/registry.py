"""Collect registration data from one or more :class:`~synchronicity.module.Module` instances."""

from __future__ import annotations

from synchronicity.module import Module


def collect_synchronized_types(modules: list[Module]) -> dict[type, tuple[str, str]]:
    """Map each registered implementation class to ``(target_module, wrapper_name)`` across modules."""
    synchronized_classes: dict[type, tuple[str, str]] = {}
    for module in modules:
        synchronized_classes.update(module._registered_classes)
    return synchronized_classes
