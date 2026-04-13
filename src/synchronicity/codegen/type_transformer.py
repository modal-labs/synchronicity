"""Type transformers for handling type signatures and wrapper/impl translation.

Each TypeTransformer encapsulates:
1. Type signature generation (wrapped_type)
2. Unwrap expressions (wrapper → impl)
3. Wrap expressions (impl → wrapper)

Transformers compose through nesting for complex types like list[Person].
"""

from __future__ import annotations

import inspect
import typing
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


class AsyncGeneratorTransformer(TypeTransformer):
    """Transformer for AsyncGenerator/AsyncIterator types."""

    def __init__(self, yield_transformer: TypeTransformer, send_type_str: str | None = "None"):
        self.yield_transformer = yield_transformer
        self.send_type_str = send_type_str

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

    def wrap_expr(self, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Return expression that wraps an async generator by calling a helper function."""
        if not self.needs_translation():
            return var_name

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
        return f"_wrap_async_gen_{sanitized}"

    def get_wrapper_helpers(self, target_module: str, indent: str = "    ") -> dict[str, str]:
        """Generate both async and sync helper functions for wrapping async generators."""
        helpers = {}

        helpers.update(self.yield_transformer.get_wrapper_helpers(target_module, indent))

        helper_name = self._get_helper_name(target_module)

        if self.yield_transformer.needs_translation():
            wrap_expr = self.yield_transformer.wrap_expr(target_module, "_item")
        else:
            wrap_expr = "_item"

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

        if wrap_expr == "_item":
            sync_helper = f"""{indent}@staticmethod
{indent}def {helper_name}_sync(_gen):
{indent}    yield from _synchronizer._run_generator_sync(_gen)"""
        else:
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


# Keep GeneratorTransformer as an alias for backward compatibility during transition
GeneratorTransformer = AsyncGeneratorTransformer


class AsyncIteratorTransformer(TypeTransformer):
    """Transformer for AsyncIterator types (not generators).

    AsyncIterator is more general than AsyncGenerator - it only has __aiter__() and __anext__(),
    not asend()/aclose(). This transformer handles iterators that aren't generators.
    """

    def __init__(self, item_transformer: TypeTransformer, runtime_package: str = "synchronicity"):
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
            f"{self._runtime_package}.types.SyncOrAsyncIterator({var_name}, "
            f"_synchronizer, item_wrapper={helper_name})"
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


class AsyncIterableTransformer(TypeTransformer):
    """Transformer for AsyncIterable[T] types.

    AsyncIterable objects have an __aiter__() method that returns an AsyncIterator.
    For sync wrappers, we convert to regular Iterable[T].
    For async wrappers, we keep AsyncIterable[T].
    """

    def __init__(self, item_transformer: TypeTransformer, runtime_package: str = "synchronicity"):
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
            f"{self._runtime_package}.types.SyncOrAsyncIterable({var_name}, "
            f"_synchronizer, item_wrapper={helper_name})"
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


class AsyncContextManagerTransformer(TypeTransformer):
    """Transformer for AsyncContextManager[T] types.

    Wraps an async context manager into SyncOrAsyncContextManager[T] which supports
    both ``with`` (sync) and ``async with`` (async) usage.
    """

    def __init__(self, value_transformer: TypeTransformer, runtime_package: str = "synchronicity"):
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

            # Check if we need typing prefix
            if origin in (list, dict, tuple, set, frozenset, type):
                # Built-in types
                return f"{origin_name}[{', '.join(formatted_args)}]"
            else:
                # typing module types
                origin_str = repr(origin)
                if "typing." in origin_str:
                    origin_name = origin_str.split(".")[-1].rstrip("'>")
                return f"typing.{origin_name}[{', '.join(formatted_args)}]"
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
