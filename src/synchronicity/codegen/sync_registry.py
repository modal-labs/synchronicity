"""Maps implementation classes (by qualified name) to wrapper module + name.

Emit and transformers use this instead of ``dict[type, ...]`` so codegen does not
need live ``type`` objects from the implementation.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from .transformer_ir import ImplQualifiedRef


class SyncRegistry(Mapping[ImplQualifiedRef, tuple[str, str]]):
    """Immutable mapping ``ImplQualifiedRef -> (wrapper_module, wrapper_name)``."""

    __slots__ = ("_m",)

    def __init__(self, by_impl_ref: dict[ImplQualifiedRef, tuple[str, str]]):
        self._m = dict(by_impl_ref)

    @classmethod
    def from_type_map(cls, synchronized_types: dict[type, tuple[str, str]]) -> SyncRegistry:
        return cls({ImplQualifiedRef(t.__module__, t.__qualname__): v for t, v in synchronized_types.items()})

    def __getitem__(self, key: ImplQualifiedRef) -> tuple[str, str]:
        return self._m[key]

    def __iter__(self) -> Iterator[ImplQualifiedRef]:
        return iter(self._m)

    def __len__(self) -> int:
        return len(self._m)

    def has_wrapped_class(self, impl_type: type) -> bool:
        ref = ImplQualifiedRef(impl_type.__module__, impl_type.__qualname__)
        return ref in self._m

    def lookup_wrapper(self, impl_type: type) -> tuple[str, str] | None:
        ref = ImplQualifiedRef(impl_type.__module__, impl_type.__qualname__)
        return self._m.get(ref)

    def with_impl_ref(self, ref: ImplQualifiedRef, wrapper_module: str, wrapper_name: str) -> SyncRegistry:
        """Copy with an extra (or replaced) mapping for ``ref`` (e.g. current class for ``Self``)."""
        m = dict(self._m)
        m[ref] = (wrapper_module, wrapper_name)
        return SyncRegistry(m)

    def with_impl_class(self, impl_type: type, wrapper_module: str, wrapper_name: str) -> SyncRegistry:
        """Copy with an extra (or replaced) mapping for ``impl_type`` (e.g. current class for ``Self``)."""
        return self.with_impl_ref(
            ImplQualifiedRef(impl_type.__module__, impl_type.__qualname__),
            wrapper_module,
            wrapper_name,
        )

    def get(self, key: ImplQualifiedRef, default=None):
        return self._m.get(key, default)
