"""IR mirroring :mod:`type_transformer` structure using qualified names, not live types.

Wrapped implementation classes and ``Self`` owners are referenced by
``(module, qualname)``. Everything else composes the same way as runtime
transformers. Emit time calls :func:`transformer_materialize.materialize_transformer_ir`.
"""

from __future__ import annotations

import dataclasses
import typing


class ImportAwareTypeIR:
    def required_import_modules(self) -> frozenset[str]:
        return frozenset()


@dataclasses.dataclass(frozen=True)
class ImplQualifiedRef:
    """``__module__`` + ``__qualname__`` of an implementation class (or type)."""

    module: str
    qualname: str


@dataclasses.dataclass(frozen=True)
class WrapperRef:
    """Resolved wrapper location: where the wrapper class lives in generated code."""

    wrapper_module: str
    wrapper_name: str


@dataclasses.dataclass(frozen=True)
class IdentityTypeIR(ImportAwareTypeIR):
    """Non-wrapped annotation; ``signature_text`` is the type as it should appear in source."""

    signature_text: str
    import_modules: tuple[str, ...] = ()

    def required_import_modules(self) -> frozenset[str]:
        return frozenset(self.import_modules)


@dataclasses.dataclass(frozen=True)
class WrappedClassTypeIR(ImportAwareTypeIR):
    """Registered wrapped class with resolved wrapper location."""

    impl: ImplQualifiedRef
    wrapper: WrapperRef

    def required_import_modules(self) -> frozenset[str]:
        return frozenset((self.wrapper.wrapper_module,))


@dataclasses.dataclass(frozen=True)
class TypeVarIR(ImportAwareTypeIR):
    """Reference to a module-level ``typing.TypeVar`` by name (bound / translation from :class:`~ir.TypeVarSpecIR`)."""

    name: str


@dataclasses.dataclass(frozen=True)
class SelfTypeIR(ImportAwareTypeIR):
    """``typing.Self`` tied to a wrapped owner class."""

    owner_impl: ImplQualifiedRef
    wrapper: WrapperRef

    def required_import_modules(self) -> frozenset[str]:
        return frozenset((self.wrapper.wrapper_module,))


@dataclasses.dataclass(frozen=True)
class ListTypeIR(ImportAwareTypeIR):
    item: TypeTransformerIR

    def required_import_modules(self) -> frozenset[str]:
        return self.item.required_import_modules()


@dataclasses.dataclass(frozen=True)
class DictTypeIR(ImportAwareTypeIR):
    key: TypeTransformerIR
    value: TypeTransformerIR

    def required_import_modules(self) -> frozenset[str]:
        return _merge_required_import_modules(self.key, self.value)


@dataclasses.dataclass(frozen=True)
class SequenceTypeIR(ImportAwareTypeIR):
    item: TypeTransformerIR

    def required_import_modules(self) -> frozenset[str]:
        return self.item.required_import_modules()


@dataclasses.dataclass(frozen=True)
class CollectionTypeIR(ImportAwareTypeIR):
    item: TypeTransformerIR

    def required_import_modules(self) -> frozenset[str]:
        return self.item.required_import_modules()


@dataclasses.dataclass(frozen=True)
class TupleTypeIR(ImportAwareTypeIR):
    """Fixed ``tuple[T1, T2]`` or variadic ``tuple[T, ...]`` (``variadic=True``, single element)."""

    elements: tuple[TypeTransformerIR, ...]
    variadic: bool

    def required_import_modules(self) -> frozenset[str]:
        return _merge_required_import_modules(*self.elements)


@dataclasses.dataclass(frozen=True)
class OptionalTypeIR(ImportAwareTypeIR):
    inner: TypeTransformerIR

    def required_import_modules(self) -> frozenset[str]:
        return self.inner.required_import_modules()


@dataclasses.dataclass(frozen=True)
class UnionTypeIR(ImportAwareTypeIR):
    items: tuple[TypeTransformerIR, ...]
    source_label: str | None = None

    def required_import_modules(self) -> frozenset[str]:
        return _merge_required_import_modules(*self.items)


@dataclasses.dataclass(frozen=True)
class AsyncGeneratorTypeIR(ImportAwareTypeIR):
    yield_item: TypeTransformerIR
    send_type_str: str | None
    send_type_import_modules: tuple[str, ...] = ()

    def required_import_modules(self) -> frozenset[str]:
        return self.yield_item.required_import_modules() | frozenset(self.send_type_import_modules)


@dataclasses.dataclass(frozen=True)
class SyncGeneratorTypeIR(ImportAwareTypeIR):
    yield_item: TypeTransformerIR

    def required_import_modules(self) -> frozenset[str]:
        return self.yield_item.required_import_modules()


@dataclasses.dataclass(frozen=True)
class AsyncIteratorTypeIR(ImportAwareTypeIR):
    item: TypeTransformerIR

    def required_import_modules(self) -> frozenset[str]:
        return self.item.required_import_modules()


@dataclasses.dataclass(frozen=True)
class AsyncIterableTypeIR(ImportAwareTypeIR):
    item: TypeTransformerIR

    def required_import_modules(self) -> frozenset[str]:
        return self.item.required_import_modules()


@dataclasses.dataclass(frozen=True)
class CoroutineTypeIR(ImportAwareTypeIR):
    return_type: TypeTransformerIR

    def required_import_modules(self) -> frozenset[str]:
        return self.return_type.required_import_modules()


@dataclasses.dataclass(frozen=True)
class AwaitableTypeIR(ImportAwareTypeIR):
    inner: TypeTransformerIR

    def required_import_modules(self) -> frozenset[str]:
        return self.inner.required_import_modules()


@dataclasses.dataclass(frozen=True)
class AsyncContextManagerTypeIR(ImportAwareTypeIR):
    value: TypeTransformerIR

    def required_import_modules(self) -> frozenset[str]:
        return self.value.required_import_modules()


@dataclasses.dataclass(frozen=True)
class CallableTypeIR(ImportAwareTypeIR):
    params: tuple[TypeTransformerIR, ...] | None
    return_type: TypeTransformerIR
    params_signature_text: str | None = None
    params_signature_import_modules: tuple[str, ...] = ()

    def required_import_modules(self) -> frozenset[str]:
        extra_modules = frozenset(self.params_signature_import_modules)
        if self.params is None:
            return self.return_type.required_import_modules() | extra_modules
        return _merge_required_import_modules(*self.params, self.return_type) | extra_modules


@dataclasses.dataclass(frozen=True)
class SubscriptedWrappedClassTypeIR(ImportAwareTypeIR):
    """Wrapped class subscripted with type arguments, e.g. ``SomeContainer[WrappedType]``."""

    impl: ImplQualifiedRef
    wrapper: WrapperRef
    type_args: tuple[TypeTransformerIR, ...]

    def required_import_modules(self) -> frozenset[str]:
        return frozenset((self.wrapper.wrapper_module,)) | _merge_required_import_modules(*self.type_args)


TypeTransformerIR = typing.Union[
    IdentityTypeIR,
    WrappedClassTypeIR,
    TypeVarIR,
    SelfTypeIR,
    ListTypeIR,
    DictTypeIR,
    SequenceTypeIR,
    CollectionTypeIR,
    TupleTypeIR,
    OptionalTypeIR,
    UnionTypeIR,
    AsyncGeneratorTypeIR,
    SyncGeneratorTypeIR,
    AsyncIteratorTypeIR,
    AsyncIterableTypeIR,
    CoroutineTypeIR,
    AwaitableTypeIR,
    AsyncContextManagerTypeIR,
    CallableTypeIR,
    SubscriptedWrappedClassTypeIR,
]


def _merge_required_import_modules(*irs: TypeTransformerIR | None) -> frozenset[str]:
    modules: set[str] = set()
    for ir in irs:
        if ir is None:
            continue
        modules.update(ir.required_import_modules())
    return frozenset(modules)
