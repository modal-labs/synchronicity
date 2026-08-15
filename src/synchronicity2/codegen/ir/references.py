"""Qualified references stored in code-generation IR."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class ImplementationRef:
    """Implementation object identified by module and qualified name."""

    module: str
    qualname: str


@dataclasses.dataclass(frozen=True)
class WrapperClassRef:
    """Intended location of a generated wrapper class."""

    wrapper_module: str
    wrapper_name: str


@dataclasses.dataclass(frozen=True)
class ModuleImportRefIR:
    """A plain module import required for an emitted expression."""

    module: str
    name: str


@dataclasses.dataclass(frozen=True)
class QualifiedObjectRefIR:
    """Importable object represented by a module and attribute path."""

    module: str
    qualname: str
