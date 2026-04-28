"""Type transformers for handling type signatures and wrapper/impl translation.

Each TypeTransformer encapsulates:
1. Type signature generation (wrapped_type)
2. Unwrap expressions (wrapper → impl)
3. Wrap expressions (impl → wrapper)

Transformers compose through nesting for complex types like list[Person].
"""

from __future__ import annotations

import dataclasses
import inspect
import re
import typing
import uuid
from abc import ABC, abstractmethod

from .ir import MethodBindingKind
from .transformer_ir import ImplQualifiedRef, WrapperRef


class TypeTransformer(ABC):
    """Base class for type transformers that handle type signatures and translation."""

    @abstractmethod
    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        """Return the type signature string for generated wrapper code.

        Args:
            target_module: Current target module (for local vs cross-module refs)
            is_async: Whether we're in an async context (affects async generator return types)

        Returns:
            Type string like "Person", "list[str]", "foo.bar.Person"
        """
        pass

    @abstractmethod
    def unwrap_expr(self, var_name: str) -> str:
        """Generate Python expression to unwrap from wrapper → impl.

        Args:
            var_name: Variable name to unwrap

        Returns:
            Expression string like "value._impl_instance" or "[x._impl_instance for x in value]"
        """
        pass

    @abstractmethod
    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Generate Python expression to wrap from impl → wrapper.

        Args:
            target_module: Current target module (for local vs cross-module refs)
            var_name: Variable name to wrap
            is_async: Whether we're in an async context (affects generator wrapping)

        Returns:
            Expression string like "Person._from_impl(value)" or "[Person._from_impl(x) for x in value]"
        """
        pass

    def needs_translation(self) -> bool:
        """Check if this type needs unwrap/wrap translation.

        Returns:
            True if this type contains wrapped classes that need translation
        """
        return False

    def get_wrapper_helpers(
        self,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Generate inline helper functions needed for wrapping this type.

        Returns a dict to enable automatic deduplication.

        Args:
            target_module: Current target module
            indent: Indentation string for the helper functions

        Returns:
            Dict mapping helper function name to helper function code.
            Empty dict for types that don't need helpers.
        """
        return {}

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        """Whether this annotation references a wrapper class defined in ``target_module``.

        Generated source must quote such annotations when they can appear before the local
        wrapper class is defined.
        """
        return False

    def annotation_type(self, target_module: str, is_async: bool = True) -> str:
        """Return the string to emit in generated annotations.

        This defaults to ``wrapped_type`` and quotes the whole expression whenever it contains
        a local wrapper reference that may otherwise be a forward reference at import time.
        """
        wrapped = self.wrapped_type(target_module, is_async)
        if self.has_local_wrapper_ref(target_module):
            return f'"{wrapped}"'
        return wrapped

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        """Return the impl-facing annotation string for passthrough values.

        This is used for container annotations like ``Callable`` where Synchronicity does not
        currently wrap or unwrap the inner runtime value, so the public wrapper annotation needs
        to describe the implementation-facing contract rather than the translated wrapper-facing one.
        """
        return self.annotation_type(target_module, is_async)


class IdentityStrTransformer(TypeTransformer):
    """Like :class:`IdentityTransformer` but stores only the preformatted type string."""

    def __init__(self, signature_text: str):
        self._signature_text = signature_text

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        return self._signature_text

    def unwrap_expr(self, var_name: str) -> str:
        return var_name

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        return var_name

    def needs_translation(self) -> bool:
        return False


class IdentityTransformer(TypeTransformer):
    """Transformer for types that don't need translation (primitives, etc.)."""

    def __init__(self, annotation):
        self.annotation = annotation

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        """Format the type annotation as-is."""
        return _format_annotation_str(self.annotation)

    def unwrap_expr(self, var_name: str) -> str:
        """No unwrapping needed - return variable as-is."""
        return var_name

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """No wrapping needed - return variable as-is."""
        return var_name

    def needs_translation(self) -> bool:
        return False


class WrappedClassTransformer(TypeTransformer):
    """Transformer for wrapped class types."""

    def __init__(self, impl: ImplQualifiedRef, wrapper: WrapperRef):
        self.impl_ref = impl
        self._wrapper = wrapper

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        """Return the wrapper class name (local or fully qualified)."""
        if self._wrapper.wrapper_module == target_module:
            return self._wrapper.wrapper_name
        else:
            return f"{self._wrapper.wrapper_module}.{self._wrapper.wrapper_name}"

    def unwrap_expr(self, var_name: str) -> str:
        """Unwrap by accessing _impl_instance."""
        return f"{var_name}._impl_instance"

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Wrap by calling WrapperClass._from_impl()."""
        if self._wrapper.wrapper_module == target_module:
            return f"{self._wrapper.wrapper_name}._from_impl({var_name})"
        else:
            return f"{self._wrapper.wrapper_module}.{self._wrapper.wrapper_name}._from_impl({var_name})"

    def needs_translation(self) -> bool:
        return True

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return self._wrapper.wrapper_module == target_module

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        return _impl_ref_dotted(self.impl_ref)


class SubscriptedWrappedClassTransformer(TypeTransformer):
    """Wrapped class subscripted with type args, e.g. ``SomeContainer[WrappedType]``.

    Unwrap/wrap delegates to the base :class:`WrappedClassTransformer`; the type
    arguments only affect the annotation string.
    """

    def __init__(
        self,
        impl: ImplQualifiedRef,
        wrapper: WrapperRef,
        type_arg_transformers: list[TypeTransformer],
    ):
        self._inner = WrappedClassTransformer(impl, wrapper)
        self._type_arg_transformers = type_arg_transformers

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        base = self._inner.wrapped_type(target_module, is_async)
        args = ", ".join(t.wrapped_type(target_module, is_async) for t in self._type_arg_transformers)
        return f"{base}[{args}]"

    def unwrap_expr(self, var_name: str) -> str:
        return self._inner.unwrap_expr(var_name)

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        return self._inner.wrap_expr(target_module, var_name, is_async)

    def needs_translation(self) -> bool:
        return True

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return self._inner.has_local_wrapper_ref(target_module) or any(
            t.has_local_wrapper_ref(target_module) for t in self._type_arg_transformers
        )

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        base = _impl_ref_dotted(self._inner.impl_ref)
        args = ", ".join(t.passthrough_annotation_type(target_module, is_async) for t in self._type_arg_transformers)
        return f"{base}[{args}]"


class TypeVarBoundTransformer(TypeTransformer):
    """Type variable: signature shows *name* (e.g. ``T``); unwrap/wrap follows the bound type transformer."""

    def __init__(self, name: str, bound_transformer: TypeTransformer):
        self._name = name
        self._bound = bound_transformer

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        return self._name

    def unwrap_expr(self, var_name: str) -> str:
        return self._bound.unwrap_expr(var_name)

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        inner = self._bound.wrap_expr(target_module, var_name, is_async)
        return f"typing.cast({self._name}, {inner})"

    def needs_translation(self) -> bool:
        return True

    def get_wrapper_helpers(
        self,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        return self._bound.get_wrapper_helpers(target_module, indent)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        return self._name


class SelfTransformer(TypeTransformer):
    """``typing.Self`` on a synchronized class: unwrap/wrap like the wrapper type, but keep ``typing.Self``
    in signatures.

    Emitting the concrete wrapper name would break ``Self`` binding on subclasses and on generic classes.
    """

    def __init__(self, impl: ImplQualifiedRef, wrapper: WrapperRef):
        self._impl = WrappedClassTransformer(impl, wrapper)

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        return "typing.Self"

    def unwrap_expr(self, var_name: str) -> str:
        return self._impl.unwrap_expr(var_name)

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        return self._impl.wrap_expr(target_module, var_name, is_async)

    def wrap_expr_for_method(
        self,
        target_module: str,
        var_name: str,
        *,
        is_async: bool,
        method_type: MethodBindingKind,
    ) -> str:
        """Runtime wrap for ``typing.Self`` (``_from_impl`` is a classmethod; call via ``self`` / ``cls``)."""
        if method_type == MethodBindingKind.CLASSMETHOD:
            binding = "cls"
        elif method_type == MethodBindingKind.STATICMETHOD:
            return self._impl.wrap_expr(target_module, var_name, is_async)
        else:
            binding = "self"
        return f"typing.cast(typing.Self, {binding}._from_impl({var_name}))"

    def needs_translation(self) -> bool:
        return True

    def get_wrapper_helpers(
        self,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        return self._impl.get_wrapper_helpers(target_module, indent)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        return _impl_ref_dotted(self._impl.impl_ref)


class ListTransformer(TypeTransformer):
    """Transformer for list[T] types."""

    def __init__(self, item_transformer: TypeTransformer):
        self.item_transformer = item_transformer

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        """Return list[WrappedItemType]."""
        item_type_str = self.item_transformer.wrapped_type(target_module, is_async)
        return f"list[{item_type_str}]"

    def unwrap_expr(self, var_name: str) -> str:
        """Generate list comprehension to unwrap items."""
        if not self.item_transformer.needs_translation():
            return var_name

        item_unwrap = self.item_transformer.unwrap_expr("x")
        return f"[{item_unwrap} for x in {var_name}]"

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Generate list comprehension to wrap items."""
        if not self.item_transformer.needs_translation():
            return var_name

        item_wrap = self.item_transformer.wrap_expr(target_module, "x", is_async)
        expr = f"[{item_wrap} for x in {var_name}]"
        if isinstance(self.item_transformer, TypeVarBoundTransformer):
            ann = self.wrapped_type(target_module, is_async)
            return f"typing.cast({ann}, {expr})"
        return expr

    def needs_translation(self) -> bool:
        return self.item_transformer.needs_translation()

    def get_wrapper_helpers(
        self,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Recursively collect helpers from item transformer."""
        return self.item_transformer.get_wrapper_helpers(target_module, indent)

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return self.item_transformer.has_local_wrapper_ref(target_module)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        item_type_str = self.item_transformer.passthrough_annotation_type(target_module, is_async)
        return f"list[{item_type_str}]"


class DictTransformer(TypeTransformer):
    """Transformer for dict[K, V] types."""

    def __init__(self, key_transformer: TypeTransformer, value_transformer: TypeTransformer):
        self.key_transformer = key_transformer
        self.value_transformer = value_transformer

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        """Return dict[WrappedKeyType, WrappedValueType]."""
        key_type_str = self.key_transformer.wrapped_type(target_module, is_async)
        value_type_str = self.value_transformer.wrapped_type(target_module, is_async)
        return f"dict[{key_type_str}, {value_type_str}]"

    def unwrap_expr(self, var_name: str) -> str:
        """Generate dict comprehension to unwrap values."""
        if not self.value_transformer.needs_translation():
            return var_name

        value_unwrap = self.value_transformer.unwrap_expr("v")
        return f"{{k: {value_unwrap} for k, v in {var_name}.items()}}"

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Generate dict comprehension to wrap values."""
        if not self.value_transformer.needs_translation():
            return var_name

        value_wrap = self.value_transformer.wrap_expr(target_module, "v", is_async)
        return f"{{k: {value_wrap} for k, v in {var_name}.items()}}"

    def needs_translation(self) -> bool:
        return self.value_transformer.needs_translation()

    def get_wrapper_helpers(
        self,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Recursively collect helpers from key and value transformers."""
        helpers = {}
        helpers.update(self.key_transformer.get_wrapper_helpers(target_module, indent))
        helpers.update(self.value_transformer.get_wrapper_helpers(target_module, indent))
        return helpers

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return self.key_transformer.has_local_wrapper_ref(
            target_module
        ) or self.value_transformer.has_local_wrapper_ref(target_module)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        key_type_str = self.key_transformer.passthrough_annotation_type(target_module, is_async)
        value_type_str = self.value_transformer.passthrough_annotation_type(target_module, is_async)
        return f"dict[{key_type_str}, {value_type_str}]"


class SequenceTransformer(TypeTransformer):
    """Transformer for typing.Sequence[T]."""

    def __init__(self, item_transformer: TypeTransformer):
        self.item_transformer = item_transformer

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        item_type_str = self.item_transformer.wrapped_type(target_module, is_async)
        return f"typing.Sequence[{item_type_str}]"

    def unwrap_expr(self, var_name: str) -> str:
        if not self.item_transformer.needs_translation():
            return var_name
        item_unwrap = self.item_transformer.unwrap_expr("x")
        return f"[{item_unwrap} for x in {var_name}]"

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        if not self.item_transformer.needs_translation():
            return var_name
        item_wrap = self.item_transformer.wrap_expr(target_module, "x", is_async)
        expr = f"[{item_wrap} for x in {var_name}]"
        if isinstance(self.item_transformer, TypeVarBoundTransformer):
            ann = self.wrapped_type(target_module, is_async)
            return f"typing.cast({ann}, {expr})"
        return expr

    def needs_translation(self) -> bool:
        return self.item_transformer.needs_translation()

    def get_wrapper_helpers(
        self,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        return self.item_transformer.get_wrapper_helpers(target_module, indent)

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return self.item_transformer.has_local_wrapper_ref(target_module)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        item_type_str = self.item_transformer.passthrough_annotation_type(target_module, is_async)
        return f"typing.Sequence[{item_type_str}]"


class TupleTransformer(TypeTransformer):
    """Transformer for tuple types - both fixed-size tuple[T1, T2] and variable-length tuple[T, ...]."""

    def __init__(self, item_transformers: list[TypeTransformer]):
        """
        Args:
            item_transformers: List of transformers for each tuple element.
                               If all elements are the same type, this can be a single-item list.
        """
        self.item_transformers = item_transformers

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        """Return tuple[WrappedType1, WrappedType2, ...] or tuple[WrappedType, ...]."""
        if len(self.item_transformers) == 1:
            item_type_str = self.item_transformers[0].wrapped_type(target_module, is_async)
            return f"tuple[{item_type_str}, ...]"
        else:
            item_type_strs = [t.wrapped_type(target_module, is_async) for t in self.item_transformers]
            return f"tuple[{', '.join(item_type_strs)}]"

    def unwrap_expr(self, var_name: str) -> str:
        """Generate tuple comprehension/constructor to unwrap items."""
        if not self.needs_translation():
            return var_name

        if len(self.item_transformers) == 1:
            item_unwrap = self.item_transformers[0].unwrap_expr("x")
            return f"tuple({item_unwrap} for x in {var_name})"
        else:
            unwrap_exprs = [t.unwrap_expr(f"{var_name}[{i}]") for i, t in enumerate(self.item_transformers)]
            return f"({', '.join(unwrap_exprs)})"

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Generate tuple comprehension/constructor to wrap items."""
        if not self.needs_translation():
            return var_name

        if len(self.item_transformers) == 1:
            item_wrap = self.item_transformers[0].wrap_expr(target_module, "x", is_async)
            expr = f"tuple({item_wrap} for x in {var_name})"
        else:
            wrap_exprs = [
                t.wrap_expr(target_module, f"{var_name}[{i}]", is_async) for i, t in enumerate(self.item_transformers)
            ]
            expr = f"({', '.join(wrap_exprs)})"
        if any(isinstance(t, TypeVarBoundTransformer) for t in self.item_transformers):
            ann = self.wrapped_type(target_module, is_async)
            return f"typing.cast({ann}, {expr})"
        return expr

    def needs_translation(self) -> bool:
        return any(t.needs_translation() for t in self.item_transformers)

    def get_wrapper_helpers(
        self,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Recursively collect helpers from all item transformers."""
        helpers = {}
        for transformer in self.item_transformers:
            helpers.update(transformer.get_wrapper_helpers(target_module, indent))
        return helpers

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return any(transformer.has_local_wrapper_ref(target_module) for transformer in self.item_transformers)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        if len(self.item_transformers) == 1:
            item_type_str = self.item_transformers[0].passthrough_annotation_type(target_module, is_async)
            return f"tuple[{item_type_str}, ...]"
        item_type_strs = [t.passthrough_annotation_type(target_module, is_async) for t in self.item_transformers]
        return f"tuple[{', '.join(item_type_strs)}]"


class OptionalTransformer(TypeTransformer):
    """Transformer for Optional[T] (Union[T, None]) types."""

    def __init__(self, inner_transformer: TypeTransformer):
        self.inner_transformer = inner_transformer

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        """Return typing.Union[WrappedInnerType, None]."""
        inner_type_str = self.inner_transformer.wrapped_type(target_module, is_async)
        return f"typing.Union[{inner_type_str}, None]"

    def unwrap_expr(self, var_name: str) -> str:
        """Generate conditional expression to unwrap if not None."""
        if not self.inner_transformer.needs_translation():
            return var_name

        inner_unwrap = self.inner_transformer.unwrap_expr(var_name)
        return f"{inner_unwrap} if {var_name} is not None else None"

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Generate conditional expression to wrap if not None."""
        if not self.inner_transformer.needs_translation():
            return var_name

        inner_wrap = self.inner_transformer.wrap_expr(target_module, var_name, is_async)
        return f"{inner_wrap} if {var_name} is not None else None"

    def needs_translation(self) -> bool:
        return self.inner_transformer.needs_translation()

    def get_wrapper_helpers(
        self,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Recursively collect helpers from inner transformer."""
        return self.inner_transformer.get_wrapper_helpers(target_module, indent)

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return self.inner_transformer.has_local_wrapper_ref(target_module)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        inner_type_str = self.inner_transformer.passthrough_annotation_type(target_module, is_async)
        return f"typing.Union[{inner_type_str}, None]"


@dataclasses.dataclass(frozen=True)
class _UnionArmRuntimeSpec:
    discriminator_key: tuple[str, ...] | None
    runtime_action_key: tuple[str, ...] | None
    unwrap_guard_expr: str | None
    wrap_guard_expr: str | None
    translated: bool
    unwrap_value_expr: str
    wrap_value_expr: str


def _impl_ref_dotted(impl_ref: ImplQualifiedRef) -> str:
    q = impl_ref.qualname
    if ".<locals>." in q or q.startswith("<locals>."):
        return f"{impl_ref.module}.{q.rpartition('.')[2]}"
    return f"{impl_ref.module}.{q}"


def _identity_runtime_expr(signature_text: str) -> str | None:
    if signature_text in {"None", "int", "str", "bool", "float", "bytes", "complex"}:
        return signature_text
    if signature_text.startswith("typing."):
        return None
    if "[" in signature_text or "]" in signature_text or " " in signature_text or "|" in signature_text:
        return None
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\.]*", signature_text):
        return None
    return signature_text


def _runtime_action_key(transformer: TypeTransformer) -> tuple[str, ...] | None:
    if isinstance(transformer, IdentityStrTransformer):
        return ("identity", transformer._signature_text)

    if isinstance(transformer, IdentityTransformer):
        return ("identity", _format_annotation_str(transformer.annotation))

    if isinstance(transformer, WrappedClassTransformer):
        return ("wrapped_impl", transformer.impl_ref.module, transformer.impl_ref.qualname)

    if isinstance(transformer, SubscriptedWrappedClassTransformer):
        inner = transformer._inner
        return ("wrapped_impl", inner.impl_ref.module, inner.impl_ref.qualname)

    if isinstance(transformer, TypeVarBoundTransformer):
        return _runtime_action_key(transformer._bound)

    if isinstance(transformer, SelfTransformer):
        return ("wrapped_impl", transformer._impl.impl_ref.module, transformer._impl.impl_ref.qualname)

    if isinstance(transformer, ListTransformer):
        if not transformer.needs_translation():
            return ("identity", "list")
        item_key = _runtime_action_key(transformer.item_transformer)
        if item_key is None:
            return None
        return ("list", *item_key)

    if isinstance(transformer, DictTransformer):
        if not transformer.needs_translation():
            return ("identity", "dict")
        key_key = _runtime_action_key(transformer.key_transformer)
        value_key = _runtime_action_key(transformer.value_transformer)
        if key_key is None or value_key is None:
            return None
        return ("dict", "key", *key_key, "value", *value_key)

    if isinstance(transformer, TupleTransformer):
        if not transformer.needs_translation():
            return ("identity", "tuple")
        if len(transformer.item_transformers) == 1:
            item_key = _runtime_action_key(transformer.item_transformers[0])
            if item_key is None:
                return None
            return ("tuple", "variadic", *item_key)
        parts: list[str] = ["tuple", "fixed"]
        for item_transformer in transformer.item_transformers:
            item_key = _runtime_action_key(item_transformer)
            if item_key is None:
                return None
            parts.extend(["item", *item_key])
        return tuple(parts)

    if isinstance(transformer, OptionalTransformer):
        inner_key = _runtime_action_key(transformer.inner_transformer)
        if inner_key is None:
            return None
        return ("optional", *inner_key)

    if isinstance(transformer, CallableTransformer):
        return ("callable",)

    return None


def _union_arm_runtime_spec(
    transformer: TypeTransformer,
    target_module: str,
    *,
    is_async: bool,
) -> _UnionArmRuntimeSpec:
    if isinstance(transformer, (IdentityStrTransformer, IdentityTransformer)):
        runtime_expr = _identity_runtime_expr(transformer.wrapped_type(target_module, is_async))
        if runtime_expr == "None":
            return _UnionArmRuntimeSpec(
                discriminator_key=("none",),
                runtime_action_key=_runtime_action_key(transformer),
                unwrap_guard_expr="_v is None",
                wrap_guard_expr="_v is None",
                translated=False,
                unwrap_value_expr="_v",
                wrap_value_expr="_v",
            )
        if runtime_expr is not None:
            return _UnionArmRuntimeSpec(
                discriminator_key=("identity", runtime_expr),
                runtime_action_key=_runtime_action_key(transformer),
                unwrap_guard_expr=f"isinstance(_v, {runtime_expr})",
                wrap_guard_expr=f"isinstance(_v, {runtime_expr})",
                translated=False,
                unwrap_value_expr="_v",
                wrap_value_expr="_v",
            )
        return _UnionArmRuntimeSpec(
            discriminator_key=None,
            runtime_action_key=_runtime_action_key(transformer),
            unwrap_guard_expr=None,
            wrap_guard_expr=None,
            translated=False,
            unwrap_value_expr="_v",
            wrap_value_expr="_v",
        )

    if isinstance(transformer, WrappedClassTransformer):
        impl_expr = _impl_ref_dotted(transformer.impl_ref)
        return _UnionArmRuntimeSpec(
            discriminator_key=("impl", transformer.impl_ref.module, transformer.impl_ref.qualname),
            runtime_action_key=_runtime_action_key(transformer),
            unwrap_guard_expr=(
                f'hasattr(_v, "_impl_instance") and isinstance(getattr(_v, "_impl_instance"), {impl_expr})'
            ),
            wrap_guard_expr=f"isinstance(_v, {impl_expr})",
            translated=True,
            unwrap_value_expr='getattr(_v, "_impl_instance")',
            wrap_value_expr=transformer.wrap_expr(target_module, "_v", is_async),
        )

    if isinstance(transformer, SubscriptedWrappedClassTransformer):
        inner = transformer._inner
        impl_expr = _impl_ref_dotted(inner.impl_ref)
        return _UnionArmRuntimeSpec(
            discriminator_key=("impl", inner.impl_ref.module, inner.impl_ref.qualname),
            runtime_action_key=_runtime_action_key(transformer),
            unwrap_guard_expr=(
                f'hasattr(_v, "_impl_instance") and isinstance(getattr(_v, "_impl_instance"), {impl_expr})'
            ),
            wrap_guard_expr=f"isinstance(_v, {impl_expr})",
            translated=True,
            unwrap_value_expr='getattr(_v, "_impl_instance")',
            wrap_value_expr=transformer.wrap_expr(target_module, "_v", is_async),
        )

    if isinstance(transformer, TypeVarBoundTransformer):
        spec = _union_arm_runtime_spec(transformer._bound, target_module, is_async=is_async)
        return _UnionArmRuntimeSpec(
            discriminator_key=spec.discriminator_key,
            runtime_action_key=_runtime_action_key(transformer),
            unwrap_guard_expr=spec.unwrap_guard_expr,
            wrap_guard_expr=spec.wrap_guard_expr,
            translated=True,
            unwrap_value_expr=spec.unwrap_value_expr,
            wrap_value_expr=transformer.wrap_expr(target_module, "_v", is_async),
        )

    if isinstance(transformer, SelfTransformer):
        impl_expr = _impl_ref_dotted(transformer._impl.impl_ref)
        return _UnionArmRuntimeSpec(
            discriminator_key=("impl", transformer._impl.impl_ref.module, transformer._impl.impl_ref.qualname),
            runtime_action_key=_runtime_action_key(transformer),
            unwrap_guard_expr=(
                f'hasattr(_v, "_impl_instance") and isinstance(getattr(_v, "_impl_instance"), {impl_expr})'
            ),
            wrap_guard_expr=f"isinstance(_v, {impl_expr})",
            translated=True,
            unwrap_value_expr='getattr(_v, "_impl_instance")',
            wrap_value_expr=transformer.wrap_expr(target_module, "_v", is_async),
        )

    if isinstance(transformer, ListTransformer):
        return _UnionArmRuntimeSpec(
            discriminator_key=("list",),
            runtime_action_key=_runtime_action_key(transformer),
            unwrap_guard_expr="isinstance(_v, list)",
            wrap_guard_expr="isinstance(_v, list)",
            translated=transformer.needs_translation(),
            unwrap_value_expr=transformer.unwrap_expr("_v"),
            wrap_value_expr=transformer.wrap_expr(target_module, "_v", is_async),
        )

    if isinstance(transformer, DictTransformer):
        return _UnionArmRuntimeSpec(
            discriminator_key=("dict",),
            runtime_action_key=_runtime_action_key(transformer),
            unwrap_guard_expr="isinstance(_v, dict)",
            wrap_guard_expr="isinstance(_v, dict)",
            translated=transformer.needs_translation(),
            unwrap_value_expr=transformer.unwrap_expr("_v"),
            wrap_value_expr=transformer.wrap_expr(target_module, "_v", is_async),
        )

    if isinstance(transformer, TupleTransformer):
        return _UnionArmRuntimeSpec(
            discriminator_key=("tuple",),
            runtime_action_key=_runtime_action_key(transformer),
            unwrap_guard_expr="isinstance(_v, tuple)",
            wrap_guard_expr="isinstance(_v, tuple)",
            translated=transformer.needs_translation(),
            unwrap_value_expr=transformer.unwrap_expr("_v"),
            wrap_value_expr=transformer.wrap_expr(target_module, "_v", is_async),
        )

    if isinstance(transformer, CallableTransformer):
        return _UnionArmRuntimeSpec(
            discriminator_key=("callable",),
            runtime_action_key=_runtime_action_key(transformer),
            unwrap_guard_expr='callable(_v) and not hasattr(_v, "_impl_instance")',
            wrap_guard_expr="callable(_v)",
            translated=transformer.needs_translation(),
            unwrap_value_expr=transformer.unwrap_expr("_v", target_module),
            wrap_value_expr=transformer.wrap_expr(target_module, "_v", is_async),
        )

    raise TypeError(f"Union translation does not support runtime discrimination for {type(transformer).__name__}")


class UnionTransformer(TypeTransformer):
    """Transformer for top-level ``Union[...]`` values with runtime-discriminable branches."""

    def __init__(self, item_transformers: list[TypeTransformer], source_label: str | None = None):
        self.item_transformers = item_transformers
        self.source_label = source_label

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        item_types = [t.wrapped_type(target_module, is_async) for t in self.item_transformers]
        return f"typing.Union[{', '.join(item_types)}]"

    def _error_prefix(self) -> str:
        if self.source_label:
            return f"{self.source_label}: "
        return ""

    def _arm_type_label(self, transformer: TypeTransformer) -> str:
        return transformer.wrapped_type("", is_async=True)

    def _runtime_specs(self, target_module: str, *, is_async: bool) -> list[_UnionArmRuntimeSpec]:
        specs = [_union_arm_runtime_spec(t, target_module, is_async=is_async) for t in self.item_transformers]
        if not any(spec.translated for spec in specs):
            return specs

        unique_specs: list[_UnionArmRuntimeSpec] = []
        seen: dict[tuple[str, ...], _UnionArmRuntimeSpec] = {}
        seen_labels: dict[tuple[str, ...], str] = {}
        for spec, transformer in zip(specs, self.item_transformers, strict=False):
            label = self._arm_type_label(transformer)
            if spec.discriminator_key is None:
                if spec.translated:
                    raise TypeError(
                        self._error_prefix()
                        + "Union translation requires runtime-discriminable translated arms; "
                        + f"unsupported union member {label!r}"
                    )
                unique_specs.append(spec)
                continue
            prev = seen.get(spec.discriminator_key)
            if prev is not None:
                if prev.runtime_action_key is not None and prev.runtime_action_key == spec.runtime_action_key:
                    continue
                if prev.translated or spec.translated:
                    previous_label = seen_labels[spec.discriminator_key]
                    raise TypeError(
                        self._error_prefix()
                        + "Union translation cannot disambiguate multiple arms with the same runtime shape "
                        + f"{previous_label!r} and {label!r}"
                    )
                continue
            seen[spec.discriminator_key] = spec
            seen_labels[spec.discriminator_key] = label
            unique_specs.append(spec)
        return unique_specs

    def _branch_expr(self, target_module: str, var_name: str, *, is_async: bool, for_wrap: bool) -> str:
        specs = self._runtime_specs(target_module, is_async=is_async)
        if not any(spec.translated for spec in specs):
            return var_name

        none_specs = [spec for spec in specs if spec.discriminator_key == ("none",)]
        translated_specs = [spec for spec in specs if spec.translated and spec.discriminator_key != ("none",)]
        identity_known_specs = [
            spec for spec in specs if not spec.translated and spec.discriminator_key not in {None, ("none",)}
        ]
        has_identity_fallback = any(not spec.translated and spec.discriminator_key is None for spec in specs)

        cases: list[tuple[str, str]] = []
        if none_specs:
            none_spec = none_specs[0]
            cases.append(
                (
                    none_spec.wrap_guard_expr if for_wrap else none_spec.unwrap_guard_expr,  # type: ignore[arg-type]
                    none_spec.wrap_value_expr if for_wrap else none_spec.unwrap_value_expr,
                )
            )
        for spec in translated_specs:
            guard = spec.wrap_guard_expr if for_wrap else spec.unwrap_guard_expr
            value_expr = spec.wrap_value_expr if for_wrap else spec.unwrap_value_expr
            assert guard is not None
            cases.append((guard, value_expr))
        for spec in identity_known_specs:
            guard = spec.wrap_guard_expr if for_wrap else spec.unwrap_guard_expr
            value_expr = spec.wrap_value_expr if for_wrap else spec.unwrap_value_expr
            assert guard is not None
            cases.append((guard, value_expr))

        fallback_expr = (
            "_v"
            if has_identity_fallback
            else '(_ for _ in ()).throw(TypeError(f"Unexpected value for union translation: {type(_v)!r}"))'
        )
        expr = fallback_expr
        for guard, value_expr in reversed(cases):
            expr = f"({value_expr} if {guard} else {expr})"
        return f"((lambda _v: {expr})({var_name}))"

    def unwrap_expr(self, var_name: str) -> str:
        return self._branch_expr("", var_name, is_async=True, for_wrap=False)

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        return self._branch_expr(target_module, var_name, is_async=is_async, for_wrap=True)

    def needs_translation(self) -> bool:
        return any(t.needs_translation() for t in self.item_transformers)

    def get_wrapper_helpers(
        self,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        helpers: dict[str, str] = {}
        for transformer in self.item_transformers:
            helpers.update(transformer.get_wrapper_helpers(target_module, indent))
        return helpers

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return any(transformer.has_local_wrapper_ref(target_module) for transformer in self.item_transformers)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        item_types = [t.passthrough_annotation_type(target_module, is_async) for t in self.item_transformers]
        return f"typing.Union[{', '.join(item_types)}]"


class AsyncGeneratorTransformer(TypeTransformer):
    """Transformer for AsyncGenerator/AsyncIterator types."""

    def __init__(self, yield_transformer: TypeTransformer, send_type_str: str | None = "None"):
        self.yield_transformer = yield_transformer
        self.send_type_str = send_type_str
        self._uid = uuid.uuid4().hex[:8]

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        """Return AsyncGenerator[T, S] for async context, Generator[T, S, None] for sync context."""
        yield_type_str = self.yield_transformer.wrapped_type(target_module, is_async)

        if is_async:
            if self.send_type_str is None:
                return f"typing.AsyncGenerator[{yield_type_str}]"
            else:
                return f"typing.AsyncGenerator[{yield_type_str}, {self.send_type_str}]"
        else:
            send_type_for_sync = self.send_type_str if self.send_type_str is not None else "None"
            return f"typing.Generator[{yield_type_str}, {send_type_for_sync}, None]"

    def unwrap_expr(self, var_name: str) -> str:
        """Generators don't unwrap at the parameter level."""
        return var_name

    def _needs_yield_wrapping(self) -> bool:
        """Whether yield items need translation (requiring helper generators)."""
        return self.yield_transformer.needs_translation()

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Return expression that wraps an async generator.

        When yield items don't need translation, delegates directly to the synchronizer.
        When they do, calls a generated helper function.
        """
        if not self._needs_yield_wrapping():
            if is_async:
                return f"_synchronizer._run_generator_async({var_name})"
            else:
                return f"_synchronizer._run_generator_sync({var_name})"

        helper_name = self._get_helper_name(target_module)

        if is_async:
            return f"self.{helper_name}({var_name})"
        else:
            return f"self.{helper_name}_sync({var_name})"

    def needs_translation(self) -> bool:
        """Async generators ALWAYS need translation for synchronizer integration."""
        return True

    def _get_helper_name(self, target_module: str) -> str:
        """Generate a unique helper function name for this async generator wrapper."""
        yield_type_str = self.yield_transformer.wrapped_type(target_module)
        sanitized = yield_type_str.replace("[", "_").replace("]", "").replace(".", "_").replace(", ", "_")
        return f"_wrap_async_gen_{sanitized}_{self._uid}"

    def get_wrapper_helpers(self, target_module: str, indent: str = "    ") -> dict[str, str]:
        """Generate helper functions for wrapping async generators with yield translation.

        Returns empty dict when yield items don't need translation (wrap_expr
        delegates directly to the synchronizer in that case).
        """
        if not self._needs_yield_wrapping():
            return {}

        helpers = {}

        helpers.update(self.yield_transformer.get_wrapper_helpers(target_module, indent))

        helper_name = self._get_helper_name(target_module)
        wrap_expr = self.yield_transformer.wrap_expr(target_module, "_item")

        async_helper = f"""{indent}@staticmethod
{indent}async def {helper_name}(_gen):
{indent}    _wrapped = _synchronizer._run_generator_async(_gen)
{indent}    _sent = None
{indent}    try:
{indent}        while True:
{indent}            try:
{indent}                _item = await _wrapped.asend(_sent)
{indent}                _sent = yield {wrap_expr}
{indent}            except StopAsyncIteration:
{indent}                break
{indent}    finally:
{indent}        await _wrapped.aclose()"""

        sync_helper = f"""{indent}@staticmethod
{indent}def {helper_name}_sync(_gen):
{indent}    _wrapped = _synchronizer._run_generator_sync(_gen)
{indent}    _sent = None
{indent}    try:
{indent}        while True:
{indent}            try:
{indent}                _item = _wrapped.send(_sent)
{indent}                _sent = yield {wrap_expr}
{indent}            except StopIteration:
{indent}                break
{indent}    finally:
{indent}        _wrapped.close()"""

        helpers[helper_name] = async_helper
        helpers[f"{helper_name}_sync"] = sync_helper

        return helpers

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return self.yield_transformer.has_local_wrapper_ref(target_module)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        yield_type_str = self.yield_transformer.passthrough_annotation_type(target_module, is_async)
        if is_async:
            if self.send_type_str is None:
                return f"typing.AsyncGenerator[{yield_type_str}]"
            return f"typing.AsyncGenerator[{yield_type_str}, {self.send_type_str}]"
        send_type_for_sync = self.send_type_str if self.send_type_str is not None else "None"
        return f"typing.Generator[{yield_type_str}, {send_type_for_sync}, None]"


class SyncGeneratorTransformer(TypeTransformer):
    """Transformer for sync Generator types."""

    def __init__(self, yield_transformer: TypeTransformer):
        self.yield_transformer = yield_transformer

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        """Always returns Generator[T, None, None] (ignores is_async)."""
        yield_type_str = self.yield_transformer.wrapped_type(target_module, is_async)
        return f"typing.Generator[{yield_type_str}, None, None]"

    def unwrap_expr(self, var_name: str) -> str:
        """Generators don't unwrap at the parameter level."""
        return var_name

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Return expression that wraps a sync generator."""
        if not self.needs_translation():
            return var_name

        helper_name = self._get_helper_name(target_module)
        return f"self.{helper_name}({var_name})"

    def needs_translation(self) -> bool:
        """Sync generators only need translation if yields need wrapping."""
        return self.yield_transformer.needs_translation()

    def _get_helper_name(self, target_module: str) -> str:
        """Generate a unique helper function name for this sync generator wrapper."""
        yield_type_str = self.yield_transformer.wrapped_type(target_module)
        sanitized = yield_type_str.replace("[", "_").replace("]", "").replace(".", "_").replace(", ", "_")
        return f"_wrap_gen_{sanitized}"

    def get_wrapper_helpers(self, target_module: str, indent: str = "    ") -> dict[str, str]:
        """Generate helper function for wrapping sync generators."""
        helpers = {}

        helpers.update(self.yield_transformer.get_wrapper_helpers(target_module, indent))

        if not self.needs_translation():
            return helpers

        helper_name = self._get_helper_name(target_module)

        if self.yield_transformer.needs_translation():
            wrap_expr = self.yield_transformer.wrap_expr(target_module, "_item")
        else:
            wrap_expr = "_item"

        if wrap_expr == "_item":
            helper_code = f"""{indent}@staticmethod
{indent}def {helper_name}(_gen):
{indent}    yield from _gen"""
        else:
            helper_code = f"""{indent}@staticmethod
{indent}def {helper_name}(_gen):
{indent}    _sent = None
{indent}    try:
{indent}        while True:
{indent}            try:
{indent}                _item = _gen.send(_sent)
{indent}                _sent = yield {wrap_expr}
{indent}            except StopIteration:
{indent}                break
{indent}    finally:
{indent}        _gen.close()"""
        helpers[helper_name] = helper_code

        return helpers

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return self.yield_transformer.has_local_wrapper_ref(target_module)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        yield_type_str = self.yield_transformer.passthrough_annotation_type(target_module, is_async)
        return f"typing.Generator[{yield_type_str}, None, None]"


# Keep GeneratorTransformer as an alias for backward compatibility during transition
GeneratorTransformer = AsyncGeneratorTransformer


class AsyncIteratorTransformer(TypeTransformer):
    """Transformer for AsyncIterator types (not generators).

    AsyncIterator is more general than AsyncGenerator - it only has __aiter__() and __anext__(),
    not asend()/aclose(). This transformer handles iterators that aren't generators.
    """

    def __init__(self, item_transformer: TypeTransformer, runtime_package: str = "synchronicity2"):
        self.item_transformer = item_transformer
        self._runtime_package = runtime_package

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        """Return SyncOrAsyncIterator[T] - works in both sync and async contexts."""
        item_type_str = self.item_transformer.wrapped_type(target_module, is_async)
        return f"{self._runtime_package}.types.SyncOrAsyncIterator[{item_type_str}]"

    def unwrap_expr(self, var_name: str) -> str:
        """Iterators don't unwrap at the parameter level."""
        return var_name

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Return expression that creates a SyncOrAsyncIterator wrapping an async iterator."""
        if not self.item_transformer.needs_translation():
            return f"{self._runtime_package}.types.SyncOrAsyncIterator({var_name}, _synchronizer)"

        item_wrap_expr = self.item_transformer.wrap_expr(target_module, "_item", is_async=True)
        item_wrap_expr = item_wrap_expr.replace("self.", "")

        helper_name = self._get_helper_name(target_module)
        return (
            f"{self._runtime_package}.types.SyncOrAsyncIterator({var_name}, _synchronizer, item_wrapper={helper_name})"
        )

    def needs_translation(self) -> bool:
        """AsyncIterators ALWAYS need translation to convert from async to sync."""
        return True

    def _get_helper_name(self, target_module: str) -> str:
        """Generate a unique helper function name for this async iterator wrapper."""
        item_type_str = self.item_transformer.wrapped_type(target_module)
        sanitized = item_type_str.replace("[", "_").replace("]", "").replace(".", "_").replace(", ", "_")
        return f"_wrap_async_iter_{sanitized}"

    def get_wrapper_helpers(self, target_module: str, indent: str = "    ") -> dict[str, str]:
        """Generate helper functions for wrapping iterator items if needed."""
        helpers = {}

        helpers.update(self.item_transformer.get_wrapper_helpers(target_module, indent))

        if self.item_transformer.needs_translation():
            helper_name = self._get_helper_name(target_module)
            wrap_expr = self.item_transformer.wrap_expr(target_module, "_item", is_async=True)
            wrap_expr = wrap_expr.replace("self.", "")

            helper_func = f"""def {helper_name}(_item):
    return {wrap_expr}"""

            helpers[helper_name] = helper_func

        return helpers

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return self.item_transformer.has_local_wrapper_ref(target_module)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        item_type_str = self.item_transformer.passthrough_annotation_type(target_module, is_async)
        return f"collections.abc.AsyncIterator[{item_type_str}]"


class AsyncIterableTransformer(TypeTransformer):
    """Transformer for AsyncIterable[T] types.

    AsyncIterable objects have an __aiter__() method that returns an AsyncIterator.
    For sync wrappers, we convert to regular Iterable[T].
    For async wrappers, we keep AsyncIterable[T].
    """

    def __init__(self, item_transformer: TypeTransformer, runtime_package: str = "synchronicity2"):
        """Initialize with the transformer for the item type."""
        self.item_transformer = item_transformer
        self._runtime_package = runtime_package

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        """Return SyncOrAsyncIterable[T] - works in both sync and async contexts."""
        item_type_str = self.item_transformer.wrapped_type(target_module, is_async)
        return f"{self._runtime_package}.types.SyncOrAsyncIterable[{item_type_str}]"

    def unwrap_expr(self, var_name: str) -> str:
        """No unwrapping needed for async iterables."""
        return var_name

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Return expression that creates a SyncOrAsyncIterable wrapping an async iterable."""
        if not self.item_transformer.needs_translation():
            return f"{self._runtime_package}.types.SyncOrAsyncIterable({var_name}, _synchronizer)"

        helper_suffix = (
            self.item_transformer.wrapped_type(target_module, is_async)
            .replace(".", "_")
            .replace("[", "_")
            .replace("]", "")
            .replace(", ", "_")
            .replace(" ", "")
        )
        helper_name = f"_wrap_async_iterable_item_{helper_suffix}"
        return (
            f"{self._runtime_package}.types.SyncOrAsyncIterable({var_name}, _synchronizer, item_wrapper={helper_name})"
        )

    def needs_translation(self) -> bool:
        """AsyncIterable always needs translation to provide sync/async versions."""
        return True

    def get_wrapper_helpers(self, target_module: str, indent: str = "    ") -> dict[str, str]:
        """Generate helper functions for wrapping iterable items if needed."""
        helpers = {}

        helpers.update(self.item_transformer.get_wrapper_helpers(target_module, indent))

        if self.item_transformer.needs_translation():
            wrapped_type = self.item_transformer.wrapped_type(target_module, is_async=True)
            helper_suffix = (
                wrapped_type.replace(".", "_").replace("[", "_").replace("]", "").replace(", ", "_").replace(" ", "")
            )
            helper_name = f"_wrap_async_iterable_item_{helper_suffix}"

            item_wrap_expr = self.item_transformer.wrap_expr(target_module, "_item", is_async=True)
            item_wrap_expr = item_wrap_expr.replace("self.", "")

            helper_func = f"""def {helper_name}(_item):
    return {item_wrap_expr}"""

            helpers[helper_name] = helper_func

        return helpers

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return self.item_transformer.has_local_wrapper_ref(target_module)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        item_type_str = self.item_transformer.passthrough_annotation_type(target_module, is_async)
        return f"collections.abc.AsyncIterable[{item_type_str}]"


class AsyncContextManagerTransformer(TypeTransformer):
    """Transformer for AsyncContextManager[T] types.

    Wraps an async context manager into SyncOrAsyncContextManager[T] which supports
    both ``with`` (sync) and ``async with`` (async) usage.
    """

    def __init__(self, value_transformer: TypeTransformer, runtime_package: str = "synchronicity2"):
        self.value_transformer = value_transformer
        self._runtime_package = runtime_package

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        value_type_str = self.value_transformer.wrapped_type(target_module, is_async)
        return f"{self._runtime_package}.types.SyncOrAsyncContextManager[{value_type_str}]"

    def unwrap_expr(self, var_name: str) -> str:
        return var_name

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        if not self.value_transformer.needs_translation():
            return f"{self._runtime_package}.types.SyncOrAsyncContextManager({var_name}, _synchronizer)"
        helper_name = self._get_helper_name(target_module)
        return (
            f"{self._runtime_package}.types.SyncOrAsyncContextManager({var_name}, "
            f"_synchronizer, value_wrapper=self.{helper_name})"
        )

    def needs_translation(self) -> bool:
        return True

    def _get_helper_name(self, target_module: str) -> str:
        value_type_str = self.value_transformer.wrapped_type(target_module)
        sanitized = value_type_str.replace("[", "_").replace("]", "").replace(".", "_").replace(", ", "_")
        return f"_wrap_async_cm_{sanitized}"

    def get_wrapper_helpers(self, target_module: str, indent: str = "    ") -> dict[str, str]:
        helpers = {}
        helpers.update(self.value_transformer.get_wrapper_helpers(target_module, indent))

        if self.value_transformer.needs_translation():
            helper_name = self._get_helper_name(target_module)
            wrap_expr = self.value_transformer.wrap_expr(target_module, "_item", is_async=True)
            wrap_expr = wrap_expr.replace("self.", "")

            helper_func = f"""{indent}@staticmethod
{indent}def {helper_name}(_item):
{indent}    return {wrap_expr}"""
            helpers[helper_name] = helper_func

        return helpers

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return self.value_transformer.has_local_wrapper_ref(target_module)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        value_type_str = self.value_transformer.passthrough_annotation_type(target_module, is_async)
        return f"typing.AsyncContextManager[{value_type_str}]"


class CoroutineTransformer(TypeTransformer):
    """Transformer for Coroutine[YieldType, SendType, ReturnType] types.

    When a function returns Coroutine[Any, Any, T], the wrapper functions should
    have return type T, since:
    - The async wrapper is declared as `async def` which implicitly makes it awaitable
    - The sync wrapper uses the synchronizer to unwrap and return T
    """

    def __init__(self, return_transformer: TypeTransformer):
        """Initialize with the transformer for the return type (third type arg)."""
        self.return_transformer = return_transformer

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        """Return the unwrapped return type."""
        return self.return_transformer.wrapped_type(target_module, is_async)

    def unwrap_expr(self, var_name: str) -> str:
        """No unwrapping needed - the coroutine itself is passed through."""
        return var_name

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """No wrapping needed - the coroutine itself is passed through."""
        return var_name

    def needs_translation(self) -> bool:
        """Coroutines need translation - they must be awaited/run through synchronizer."""
        return True

    def requires_await(self) -> bool:
        """Signal that this type needs to be awaited or run through synchronizer."""
        return True

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return self.return_transformer.has_local_wrapper_ref(target_module)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        return_type_str = self.return_transformer.passthrough_annotation_type(target_module, is_async)
        return f"typing.Coroutine[typing.Any, typing.Any, {return_type_str}]"


class AwaitableTransformer(TypeTransformer):
    """Transformer for Awaitable[T] types.

    When a function returns Awaitable[T], the wrapper functions should
    have return type T, since:
    - The async wrapper is declared as `async def` which implicitly makes it awaitable
    - The sync wrapper uses the synchronizer to unwrap and return T
    """

    def __init__(self, return_transformer: TypeTransformer):
        """Initialize with the transformer for the return type."""
        self.return_transformer = return_transformer

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        """Return the unwrapped return type."""
        return self.return_transformer.wrapped_type(target_module, is_async)

    def unwrap_expr(self, var_name: str) -> str:
        """No unwrapping needed - the awaitable itself is passed through."""
        return var_name

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """No wrapping needed - the awaitable itself is passed through."""
        return var_name

    def needs_translation(self) -> bool:
        """Awaitables need translation - they must be awaited/run through synchronizer."""
        return True

    def requires_await(self) -> bool:
        """Signal that this type needs to be awaited or run through synchronizer."""
        return True

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        return self.return_transformer.has_local_wrapper_ref(target_module)

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        return_type_str = self.return_transformer.passthrough_annotation_type(target_module, is_async)
        return f"typing.Awaitable[{return_type_str}]"


class CallableTransformer(TypeTransformer):
    """Transformer for typing.Callable[[...], T] and typing.Callable[..., T]."""

    def __init__(
        self,
        param_transformers: tuple[TypeTransformer, ...] | None,
        return_transformer: TypeTransformer,
        *,
        param_signature_text: str | None = None,
    ):
        self.param_transformers = param_transformers
        self.return_transformer = return_transformer
        self.param_signature_text = param_signature_text

    def wrapped_type(self, target_module: str, is_async: bool = True) -> str:
        if self.param_transformers is None:
            params_str = self.param_signature_text or "..."
        else:
            param_types = (t.wrapped_type(target_module, is_async) for t in self.param_transformers)
            params_str = f"[{', '.join(param_types)}]"
        return_type_str = self.return_transformer.wrapped_type(target_module, is_async)
        return f"typing.Callable[{params_str}, {return_type_str}]"

    def passthrough_annotation_type(self, target_module: str, is_async: bool = True) -> str:
        if self.param_transformers is None:
            params_str = self.param_signature_text or "..."
        else:
            param_types = (t.passthrough_annotation_type(target_module, is_async) for t in self.param_transformers)
            params_str = f"[{', '.join(param_types)}]"
        return_type_str = self.return_transformer.passthrough_annotation_type(target_module, is_async)
        return f"typing.Callable[{params_str}, {return_type_str}]"

    def _translated_callback_args_expr(self, target_module: str, *, wrapper_to_impl: bool) -> str:
        if self.param_transformers is None:
            return "*_callback_args, **_callback_kwargs"

        translated_args: list[str] = []
        for index, transformer in enumerate(self.param_transformers):
            arg_expr = f"_callback_args[{index}]"
            if not transformer.needs_translation():
                translated_args.append(arg_expr)
            elif wrapper_to_impl:
                if isinstance(transformer, CallableTransformer):
                    translated_args.append(transformer.unwrap_expr(arg_expr, target_module))
                else:
                    translated_args.append(transformer.unwrap_expr(arg_expr))
            else:
                translated_args.append(transformer.wrap_expr(target_module, arg_expr, is_async=False))

        translated_tuple = f"({', '.join(translated_args)}"
        if len(translated_args) == 1:
            translated_tuple += ","
        translated_tuple += ")"
        rest_tuple = f"tuple(_callback_args[{len(self.param_transformers)}:])"
        return f"*({translated_tuple} + {rest_tuple}), **_callback_kwargs"

    def unwrap_expr(self, var_name: str, target_module: str | None = None) -> str:
        return f"typing.cast(typing.Any, {var_name})"

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        callback_args = self._translated_callback_args_expr(target_module, wrapper_to_impl=True)
        call_expr = f"_impl_callable({callback_args})"
        if self.return_transformer.needs_translation():
            call_expr = self.return_transformer.wrap_expr(target_module, call_expr, is_async)
        return f"(lambda _impl_callable: " f"(lambda *_callback_args, **_callback_kwargs: {call_expr}))({var_name})"

    def needs_translation(self) -> bool:
        params_need_translation = (
            False if self.param_transformers is None else any(t.needs_translation() for t in self.param_transformers)
        )
        return params_need_translation or self.return_transformer.needs_translation()

    def has_local_wrapper_ref(self, target_module: str) -> bool:
        param_has_local_ref = (
            False
            if self.param_transformers is None
            else any(t.has_local_wrapper_ref(target_module) for t in self.param_transformers)
        )
        return param_has_local_ref or self.return_transformer.has_local_wrapper_ref(target_module)


def _is_self_annotation(annotation: object) -> bool:
    """True if annotation is typing.Self (or typing_extensions.Self when available)."""
    if annotation is typing.Self:
        return True
    try:
        import typing_extensions

        return annotation is typing_extensions.Self
    except (ImportError, AttributeError):
        return False


def _format_annotation_str(annotation) -> str:
    """Format a type annotation as a string for code generation.

    This is a simple formatter for non-wrapped types. For wrapped types,
    use the transformer's wrapped_type() method instead.
    """
    # Check for None/empty before type(None) since annotation can be the value None itself
    if annotation == inspect.Signature.empty:
        return ""

    # NoneType (from -> None annotation)
    if annotation is type(None) or annotation is None:
        return "None"

    if annotation is Ellipsis:
        return "..."

    # Handle TypeVar and ParamSpec - just return their names
    if isinstance(annotation, typing.TypeVar):
        return annotation.__name__
    if isinstance(annotation, typing.ParamSpec):
        return annotation.__name__

    # Handle lists (used in Callable parameter lists, e.g., Callable[[str, int], bool])
    if isinstance(annotation, list):
        formatted_items = [_format_annotation_str(item) for item in annotation]
        return f"[{', '.join(formatted_items)}]"

    # Handle generic types
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is not None:
        # Recursively format args
        if args:
            formatted_args = [_format_annotation_str(arg) for arg in args]

            # Get the origin name
            if hasattr(origin, "__name__"):
                origin_name = origin.__name__
            else:
                origin_name = str(origin)

            # Check if we need a module prefix
            origin_module = getattr(origin, "__module__", None)
            if origin in (list, dict, tuple, set, frozenset, type):
                # Built-in types - no prefix needed
                return f"{origin_name}[{', '.join(formatted_args)}]"
            elif origin_module in ("typing", "collections.abc"):
                # typing types and their collections.abc aliases (e.g. Callable)
                return f"typing.{origin_name}[{', '.join(formatted_args)}]"
            elif isinstance(origin, type) and origin_module not in ("builtins", "__builtin__"):
                return f"{origin.__module__}.{origin.__qualname__}[{', '.join(formatted_args)}]"
            else:
                return f"{origin_name}[{', '.join(formatted_args)}]"
        else:
            return repr(annotation)

    # Direct type
    if isinstance(annotation, type):
        if annotation.__module__ in ("builtins", "__builtin__"):
            return annotation.__name__
        else:
            return f"{annotation.__module__}.{annotation.__name__}"

    # Fallback
    return repr(annotation)
