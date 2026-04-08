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

from .sync_registry import SyncRegistry
from .transformer_ir import ImplQualifiedRef


class TypeTransformer(ABC):
    """Base class for type transformers that handle type signatures and translation."""

    @abstractmethod
    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        """Return the type signature string for generated wrapper code.

        Args:
            sync: Dict mapping implementation types to (target_module, wrapper_name)
            target_module: Current target module (for local vs cross-module refs)
            is_async: Whether we're in an async context (affects async generator return types)

        Returns:
            Type string like "Person", "list[str]", "foo.bar.Person"
        """
        pass

    @abstractmethod
    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        """Generate Python expression to unwrap from wrapper → impl.

        Args:
            sync: Dict mapping implementation types to (target_module, wrapper_name)
            var_name: Variable name to unwrap

        Returns:
            Expression string like "value._impl_instance" or "[x._impl_instance for x in value]"
        """
        pass

    @abstractmethod
    def wrap_expr(self, sync: SyncRegistry, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Generate Python expression to wrap from impl → wrapper.

        Args:
            sync: Dict mapping implementation types to (target_module, wrapper_name)
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
        sync: SyncRegistry,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Generate inline helper functions needed for wrapping this type.

        This method recursively collects helper functions from nested transformers.
        Helper functions are inlined at the beginning of each compiled function/method.

        Returns a dict to enable automatic deduplication - if multiple transformers
        generate the same helper (e.g., tuple[AsyncGenerator[str], AsyncGenerator[str]]),
        it will only appear once in the final output.

        Args:
            sync: Dict mapping implementation types to (target_module, wrapper_name)
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

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        return self._signature_text

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        return var_name

    def wrap_expr(self, sync: SyncRegistry, target_module: str, var_name: str, is_async: bool = True) -> str:
        return var_name

    def needs_translation(self) -> bool:
        return False


class IdentityTransformer(TypeTransformer):
    """Transformer for types that don't need translation (primitives, etc.)."""

    def __init__(self, annotation):
        self.annotation = annotation

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        """Format the type annotation as-is."""
        return _format_annotation_str(self.annotation)

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        """No unwrapping needed - return variable as-is."""
        return var_name

    def wrap_expr(self, sync: SyncRegistry, target_module: str, var_name: str, is_async: bool = True) -> str:
        """No wrapping needed - return variable as-is."""
        return var_name

    def needs_translation(self) -> bool:
        return False


class WrappedClassTransformer(TypeTransformer):
    """Transformer for wrapped class types."""

    def __init__(self, impl: type | ImplQualifiedRef):
        if isinstance(impl, ImplQualifiedRef):
            self.impl_ref = impl
        else:
            self.impl_ref = ImplQualifiedRef(impl.__module__, impl.__qualname__)

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        """Return the wrapper class name (local or fully qualified)."""
        if self.impl_ref not in sync:
            # Should not happen if create_transformer is used correctly
            return f"{self.impl_ref.module}.{self.impl_ref.qualname.split('.')[-1]}"

        wrapper_target_module, wrapper_name = sync[self.impl_ref]

        if wrapper_target_module == target_module:
            # Local reference
            return wrapper_name
        else:
            # Cross-module reference
            return f"{wrapper_target_module}.{wrapper_name}"

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        """Unwrap by accessing _impl_instance."""
        return f"{var_name}._impl_instance"

    def wrap_expr(self, sync: SyncRegistry, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Wrap by calling WrapperClass._from_impl()."""
        if self.impl_ref not in sync:
            return var_name

        wrapper_target_module, wrapper_name = sync[self.impl_ref]

        if wrapper_target_module == target_module:
            # Local reference
            return f"{wrapper_name}._from_impl({var_name})"
        else:
            # Cross-module reference
            return f"{wrapper_target_module}.{wrapper_name}._from_impl({var_name})"

    def needs_translation(self) -> bool:
        return True


class SelfTransformer(TypeTransformer):
    """``typing.Self`` on a synchronized class: unwrap/wrap like the wrapper type, but keep ``typing.Self``
    in signatures.

    Emitting the concrete wrapper name would break ``Self`` binding on subclasses and on generic classes.
    """

    def __init__(self, impl: type | ImplQualifiedRef):
        self._impl = WrappedClassTransformer(impl)

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        return "typing.Self"

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        return self._impl.unwrap_expr(sync, var_name)

    def wrap_expr(self, sync: SyncRegistry, target_module: str, var_name: str, is_async: bool = True) -> str:
        return self._impl.wrap_expr(sync, target_module, var_name, is_async)

    def wrap_expr_for_method(
        self,
        sync: SyncRegistry,
        target_module: str,
        var_name: str,
        *,
        is_async: bool,
        method_type: str,
    ) -> str:
        """Runtime wrap for ``typing.Self`` (``_from_impl`` is a classmethod; call via ``self`` / ``cls``)."""
        if method_type == "classmethod":
            binding = "cls"
        elif method_type == "staticmethod":
            return self._impl.wrap_expr(sync, target_module, var_name, is_async)
        else:
            binding = "self"
        return f"typing.cast(typing.Self, {binding}._from_impl({var_name}))"

    def needs_translation(self) -> bool:
        return True

    def get_wrapper_helpers(
        self,
        sync: SyncRegistry,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        return self._impl.get_wrapper_helpers(sync, target_module, indent)


class ListTransformer(TypeTransformer):
    """Transformer for list[T] types."""

    def __init__(self, item_transformer: TypeTransformer):
        self.item_transformer = item_transformer

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        """Return list[WrappedItemType]."""
        item_type_str = self.item_transformer.wrapped_type(sync, target_module, is_async)
        return f"list[{item_type_str}]"

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        """Generate list comprehension to unwrap items."""
        if not self.item_transformer.needs_translation():
            return var_name

        item_unwrap = self.item_transformer.unwrap_expr(sync, "x")
        return f"[{item_unwrap} for x in {var_name}]"

    def wrap_expr(self, sync: SyncRegistry, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Generate list comprehension to wrap items."""
        if not self.item_transformer.needs_translation():
            return var_name

        item_wrap = self.item_transformer.wrap_expr(sync, target_module, "x", is_async)
        return f"[{item_wrap} for x in {var_name}]"

    def needs_translation(self) -> bool:
        return self.item_transformer.needs_translation()

    def get_wrapper_helpers(
        self,
        sync: SyncRegistry,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Recursively collect helpers from item transformer."""
        return self.item_transformer.get_wrapper_helpers(sync, target_module, indent)


class DictTransformer(TypeTransformer):
    """Transformer for dict[K, V] types."""

    def __init__(self, key_transformer: TypeTransformer, value_transformer: TypeTransformer):
        self.key_transformer = key_transformer
        self.value_transformer = value_transformer

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        """Return dict[WrappedKeyType, WrappedValueType]."""
        key_type_str = self.key_transformer.wrapped_type(sync, target_module, is_async)
        value_type_str = self.value_transformer.wrapped_type(sync, target_module, is_async)
        return f"dict[{key_type_str}, {value_type_str}]"

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        """Generate dict comprehension to unwrap values."""
        if not self.value_transformer.needs_translation():
            return var_name

        value_unwrap = self.value_transformer.unwrap_expr(sync, "v")
        return f"{{k: {value_unwrap} for k, v in {var_name}.items()}}"

    def wrap_expr(self, sync: SyncRegistry, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Generate dict comprehension to wrap values."""
        if not self.value_transformer.needs_translation():
            return var_name

        value_wrap = self.value_transformer.wrap_expr(sync, target_module, "v", is_async)
        return f"{{k: {value_wrap} for k, v in {var_name}.items()}}"

    def needs_translation(self) -> bool:
        return self.value_transformer.needs_translation()

    def get_wrapper_helpers(
        self,
        sync: SyncRegistry,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Recursively collect helpers from key and value transformers."""
        helpers = {}
        helpers.update(self.key_transformer.get_wrapper_helpers(sync, target_module, indent))
        helpers.update(self.value_transformer.get_wrapper_helpers(sync, target_module, indent))
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

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        """Return tuple[WrappedType1, WrappedType2, ...] or tuple[WrappedType, ...]."""
        if len(self.item_transformers) == 1:
            # Variable-length tuple: tuple[T, ...]
            item_type_str = self.item_transformers[0].wrapped_type(sync, target_module, is_async)
            return f"tuple[{item_type_str}, ...]"
        else:
            # Fixed-size tuple: tuple[T1, T2, ...]
            item_type_strs = [t.wrapped_type(sync, target_module, is_async) for t in self.item_transformers]
            return f"tuple[{', '.join(item_type_strs)}]"

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        """Generate tuple comprehension/constructor to unwrap items."""
        if not self.needs_translation():
            return var_name

        if len(self.item_transformers) == 1:
            # Variable-length tuple
            item_unwrap = self.item_transformers[0].unwrap_expr(sync, "x")
            return f"tuple({item_unwrap} for x in {var_name})"
        else:
            # Fixed-size tuple - unwrap each element by index
            unwrap_exprs = [t.unwrap_expr(sync, f"{var_name}[{i}]") for i, t in enumerate(self.item_transformers)]
            return f"({', '.join(unwrap_exprs)})"

    def wrap_expr(self, sync: SyncRegistry, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Generate tuple comprehension/constructor to wrap items."""
        if not self.needs_translation():
            return var_name

        if len(self.item_transformers) == 1:
            # Variable-length tuple
            item_wrap = self.item_transformers[0].wrap_expr(sync, target_module, "x", is_async)
            return f"tuple({item_wrap} for x in {var_name})"
        else:
            # Fixed-size tuple - wrap each element by index
            wrap_exprs = [
                t.wrap_expr(sync, target_module, f"{var_name}[{i}]", is_async)
                for i, t in enumerate(self.item_transformers)
            ]
            return f"({', '.join(wrap_exprs)})"

    def needs_translation(self) -> bool:
        return any(t.needs_translation() for t in self.item_transformers)

    def get_wrapper_helpers(
        self,
        sync: SyncRegistry,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Recursively collect helpers from all item transformers."""
        helpers = {}
        for transformer in self.item_transformers:
            helpers.update(transformer.get_wrapper_helpers(sync, target_module, indent))
        return helpers


class OptionalTransformer(TypeTransformer):
    """Transformer for Optional[T] (Union[T, None]) types."""

    def __init__(self, inner_transformer: TypeTransformer):
        self.inner_transformer = inner_transformer

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        """Return typing.Union[WrappedInnerType, None]."""
        inner_type_str = self.inner_transformer.wrapped_type(sync, target_module, is_async)
        return f"typing.Union[{inner_type_str}, None]"

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        """Generate conditional expression to unwrap if not None."""
        if not self.inner_transformer.needs_translation():
            return var_name

        inner_unwrap = self.inner_transformer.unwrap_expr(sync, var_name)
        return f"{inner_unwrap} if {var_name} is not None else None"

    def wrap_expr(self, sync: SyncRegistry, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Generate conditional expression to wrap if not None."""
        if not self.inner_transformer.needs_translation():
            return var_name

        inner_wrap = self.inner_transformer.wrap_expr(sync, target_module, var_name, is_async)
        return f"{inner_wrap} if {var_name} is not None else None"

    def needs_translation(self) -> bool:
        return self.inner_transformer.needs_translation()

    def get_wrapper_helpers(
        self,
        sync: SyncRegistry,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Recursively collect helpers from inner transformer."""
        return self.inner_transformer.get_wrapper_helpers(sync, target_module, indent)


class AsyncGeneratorTransformer(TypeTransformer):
    """Transformer for AsyncGenerator/AsyncIterator types."""

    def __init__(self, yield_transformer: TypeTransformer, send_type_str: str | None = "None"):
        self.yield_transformer = yield_transformer
        self.send_type_str = send_type_str

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        """Return AsyncGenerator[T, S] for async context, Generator[T, S, None] for sync context.

        Note: Both async and sync generators preserve the send type to support two-way generators.
        """
        yield_type_str = self.yield_transformer.wrapped_type(sync, target_module, is_async)

        if is_async:
            # Async context: return AsyncGenerator[YieldType, SendType]
            if self.send_type_str is None:
                return f"typing.AsyncGenerator[{yield_type_str}]"
            else:
                return f"typing.AsyncGenerator[{yield_type_str}, {self.send_type_str}]"
        else:
            # Sync context: return Generator[YieldType, SendType, None]
            # Preserve send type to support two-way generators in sync context
            send_type_for_sync = self.send_type_str if self.send_type_str is not None else "None"
            return f"typing.Generator[{yield_type_str}, {send_type_for_sync}, None]"

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        """Generators don't unwrap at the parameter level."""
        return var_name

    def wrap_expr(
        self,
        sync: SyncRegistry,
        target_module: str,
        var_name: str,
        is_async: bool = True,
    ) -> str:
        """Return expression that wraps an async generator by calling a helper function.

        Args:
            sync: Dict mapping implementation types to (target_module, wrapper_name)
            target_module: Current target module
            var_name: Variable name to wrap
            is_async: Whether we're in an async context (determines which helper to call)
        """
        if not self.needs_translation():
            return var_name

        helper_name = self._get_helper_name(sync, target_module)

        # Use sync or async helper based on context
        if is_async:
            return f"self.{helper_name}({var_name})"
        else:
            return f"self.{helper_name}_sync({var_name})"

    def needs_translation(self) -> bool:
        """Async generators ALWAYS need translation for synchronizer integration."""
        return True

    def _get_helper_name(self, sync: SyncRegistry, target_module: str) -> str:
        """Generate a unique helper function name for this async generator wrapper."""
        yield_type_str = self.yield_transformer.wrapped_type(sync, target_module)
        sanitized = yield_type_str.replace("[", "_").replace("]", "").replace(".", "_").replace(", ", "_")
        return f"_wrap_async_gen_{sanitized}"

    def get_wrapper_helpers(
        self,
        sync: SyncRegistry,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Generate both async and sync helper functions for wrapping async generators."""
        helpers = {}

        # First, collect helpers from yield transformer (for nested cases)
        helpers.update(self.yield_transformer.get_wrapper_helpers(sync, target_module, indent))

        helper_name = self._get_helper_name(sync, target_module)

        # Check if yield items need wrapping
        if self.yield_transformer.needs_translation():
            wrap_expr = self.yield_transformer.wrap_expr(sync, target_module, "_item")
        else:
            wrap_expr = "_item"

        # Generate both async and sync helpers with send() support
        # For two-way generators, we need to manually iterate using asend()/send()
        # to preserve the bidirectional communication
        # Wrap in try/finally to ensure aclose() is forwarded properly
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

        # For sync helper, use yield from if no wrapping needed (more efficient)
        # Note: yield from automatically forwards close(), so no try/finally needed
        if wrap_expr == "_item":
            sync_helper = f"""{indent}@staticmethod
{indent}def {helper_name}_sync(_gen):
{indent}    yield from _synchronizer._run_generator_sync(_gen)"""
        else:
            # When wrapping is needed, use try/finally to ensure close() is forwarded
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

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        """Always returns Generator[T, None, None] (ignores is_async)."""
        yield_type_str = self.yield_transformer.wrapped_type(sync, target_module, is_async)
        return f"typing.Generator[{yield_type_str}, None, None]"

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        """Generators don't unwrap at the parameter level."""
        return var_name

    def wrap_expr(
        self,
        sync: SyncRegistry,
        target_module: str,
        var_name: str,
        is_async: bool = True,
    ) -> str:
        """Return expression that wraps a sync generator.

        Args:
            sync: Dict mapping implementation types to (target_module, wrapper_name)
            target_module: Current target module
            var_name: Variable name to wrap
            is_async: Ignored for sync generators (always use same helper)
        """
        if not self.needs_translation():
            return var_name

        helper_name = self._get_helper_name(sync, target_module)
        return f"self.{helper_name}({var_name})"

    def needs_translation(self) -> bool:
        """Sync generators only need translation if yields need wrapping."""
        return self.yield_transformer.needs_translation()

    def _get_helper_name(self, sync: SyncRegistry, target_module: str) -> str:
        """Generate a unique helper function name for this sync generator wrapper."""
        yield_type_str = self.yield_transformer.wrapped_type(sync, target_module)
        sanitized = yield_type_str.replace("[", "_").replace("]", "").replace(".", "_").replace(", ", "_")
        return f"_wrap_gen_{sanitized}"

    def get_wrapper_helpers(
        self,
        sync: SyncRegistry,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Generate helper function for wrapping sync generators."""
        helpers = {}

        # First, collect helpers from yield transformer (for nested cases)
        helpers.update(self.yield_transformer.get_wrapper_helpers(sync, target_module, indent))

        if not self.needs_translation():
            return helpers

        helper_name = self._get_helper_name(sync, target_module)

        # Check if yield items need wrapping
        if self.yield_transformer.needs_translation():
            wrap_expr = self.yield_transformer.wrap_expr(sync, target_module, "_item")
        else:
            wrap_expr = "_item"

        # Generate sync helper with send() support
        # Use yield from if no wrapping needed (automatically forwards send() and close())
        if wrap_expr == "_item":
            helper_code = f"""{indent}@staticmethod
{indent}def {helper_name}(_gen):
{indent}    yield from _gen"""
        else:
            # Manual iteration with send() to preserve bidirectional communication while wrapping
            # Wrap in try/finally to ensure close() is forwarded
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

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        """Return SyncOrAsyncIterator[T] - works in both sync and async contexts."""
        item_type_str = self.item_transformer.wrapped_type(sync, target_module, is_async)
        return f"{self._runtime_package}.types.SyncOrAsyncIterator[{item_type_str}]"

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        """Iterators don't unwrap at the parameter level."""
        return var_name

    def wrap_expr(
        self,
        sync: SyncRegistry,
        target_module: str,
        var_name: str,
        is_async: bool = True,
    ) -> str:
        """Return expression that creates a SyncOrAsyncIterator wrapping an async iterator."""
        if not self.item_transformer.needs_translation():
            # Items don't need wrapping
            return f"{self._runtime_package}.types.SyncOrAsyncIterator({var_name}, " f"_synchronizer)"

        # Items need wrapping - create a wrapper function
        item_wrap_expr = self.item_transformer.wrap_expr(sync, target_module, "_item", is_async=True)
        # Remove "self." prefix if present (for module-level functions)
        item_wrap_expr = item_wrap_expr.replace("self.", "")

        helper_name = self._get_helper_name(sync, target_module)
        return (
            f"{self._runtime_package}.types.SyncOrAsyncIterator({var_name}, "
            f"_synchronizer, item_wrapper={helper_name})"
        )

    def needs_translation(self) -> bool:
        """AsyncIterators ALWAYS need translation to convert from async to sync."""
        return True

    def _get_helper_name(self, sync: SyncRegistry, target_module: str) -> str:
        """Generate a unique helper function name for this async iterator wrapper."""
        item_type_str = self.item_transformer.wrapped_type(sync, target_module)
        sanitized = item_type_str.replace("[", "_").replace("]", "").replace(".", "_").replace(", ", "_")
        return f"_wrap_async_iter_{sanitized}"

    def get_wrapper_helpers(
        self,
        sync: SyncRegistry,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Generate helper functions for wrapping iterator items if needed."""
        helpers = {}

        # First, collect helpers from item transformer (for nested cases)
        helpers.update(self.item_transformer.get_wrapper_helpers(sync, target_module, indent))

        if self.item_transformer.needs_translation():
            # Generate a simple wrapper function for items
            helper_name = self._get_helper_name(sync, target_module)
            wrap_expr = self.item_transformer.wrap_expr(sync, target_module, "_item", is_async=True)
            # Remove "self." prefix for module-level functions
            wrap_expr = wrap_expr.replace("self.", "")

            # Generate a lambda-style wrapper function
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

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        """Return SyncOrAsyncIterable[T] - works in both sync and async contexts."""
        item_type_str = self.item_transformer.wrapped_type(sync, target_module, is_async)
        return f"{self._runtime_package}.types.SyncOrAsyncIterable[{item_type_str}]"

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        """No unwrapping needed for async iterables."""
        return var_name

    def wrap_expr(self, sync: SyncRegistry, target_module: str, var_name: str, is_async: bool = True) -> str:
        """Return expression that creates a SyncOrAsyncIterable wrapping an async iterable."""
        if not self.item_transformer.needs_translation():
            # Items don't need wrapping
            return f"{self._runtime_package}.types.SyncOrAsyncIterable({var_name}, " f"_synchronizer)"

        # Items need wrapping - create a wrapper function
        helper_suffix = (
            self.item_transformer.wrapped_type(sync, target_module, is_async)
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

    def get_wrapper_helpers(
        self,
        sync: SyncRegistry,
        target_module: str,
        indent: str = "    ",
    ) -> dict[str, str]:
        """Generate helper functions for wrapping iterable items if needed."""
        helpers = {}

        # First, collect helpers from item transformer (for nested cases)
        helpers.update(self.item_transformer.get_wrapper_helpers(sync, target_module, indent))

        if self.item_transformer.needs_translation():
            # Generate a simple wrapper function for items
            wrapped_type = self.item_transformer.wrapped_type(sync, target_module, is_async=True)
            helper_suffix = (
                wrapped_type.replace(".", "_").replace("[", "_").replace("]", "").replace(", ", "_").replace(" ", "")
            )
            helper_name = f"_wrap_async_iterable_item_{helper_suffix}"

            item_wrap_expr = self.item_transformer.wrap_expr(sync, target_module, "_item", is_async=True)
            # Remove "self." prefix for module-level functions
            item_wrap_expr = item_wrap_expr.replace("self.", "")

            # Generate a lambda-style wrapper function
            helper_func = f"""def {helper_name}(_item):
    return {item_wrap_expr}"""

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

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        """Return the unwrapped return type."""
        return self.return_transformer.wrapped_type(sync, target_module, is_async)

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        """No unwrapping needed - the coroutine itself is passed through."""
        return var_name

    def wrap_expr(self, sync: SyncRegistry, target_module: str, var_name: str, is_async: bool = True) -> str:
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

    def wrapped_type(self, sync: SyncRegistry, target_module: str, is_async: bool = True) -> str:
        """Return the unwrapped return type."""
        return self.return_transformer.wrapped_type(sync, target_module, is_async)

    def unwrap_expr(self, sync: SyncRegistry, var_name: str) -> str:
        """No unwrapping needed - the awaitable itself is passed through."""
        return var_name

    def wrap_expr(self, sync: SyncRegistry, target_module: str, var_name: str, is_async: bool = True) -> str:
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


def create_transformer(
    annotation,
    sync: SyncRegistry,
    runtime_package: str = "synchronicity",
    *,
    owner_impl_type: type | None = None,
    owner_has_type_parameters: bool = False,
) -> TypeTransformer:
    """Create a transformer from a type annotation.

    Args:
        annotation: Type annotation (resolved with eval_str=True)
        sync: Dict mapping implementation types to (target_module, wrapper_name)
        runtime_package: Dotted import path for generated references to synchronicity runtime
            (``types``, ``descriptor``, ``synchronizer`` submodules).
        owner_impl_type: Implementation class that owns the signature (for resolving ``typing.Self``).
        owner_has_type_parameters: If True, ``Self`` stays as ``typing.Self`` in annotations (generic classes).

    Returns:
        TypeTransformer instance (possibly nested for complex types)
    """
    # Handle empty/None annotations
    if annotation == inspect.Signature.empty or annotation is None:
        return IdentityTransformer(annotation)

    # Check for ForwardRef - should be resolved by inspect.get_annotations(eval_str=True)
    if hasattr(annotation, "__forward_arg__"):
        forward_str = annotation.__forward_arg__
        raise TypeError(
            f"Found unresolved forward reference '{forward_str}' in type annotation. "
            f"Use inspect.get_annotations(eval_str=True) to resolve forward references."
        )

    # Direct wrapped class type
    if isinstance(annotation, type) and sync.has_wrapped_class(annotation):
        return WrappedClassTransformer(annotation)

    # Check for generic types
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is None:
        if _is_self_annotation(annotation) and owner_impl_type is not None and sync.has_wrapped_class(owner_impl_type):
            return SelfTransformer(owner_impl_type)
        # Non-generic type (primitive or non-wrapped class)
        return IdentityTransformer(annotation)

    # List[T]
    if origin is list:
        if args:
            item_transformer = create_transformer(
                args[0],
                sync,
                runtime_package,
                owner_impl_type=owner_impl_type,
                owner_has_type_parameters=owner_has_type_parameters,
            )
            return ListTransformer(item_transformer)
        else:
            return IdentityTransformer(annotation)

    # Dict[K, V]
    if origin is dict:
        if len(args) >= 2:
            key_transformer = create_transformer(
                args[0],
                sync,
                runtime_package,
                owner_impl_type=owner_impl_type,
                owner_has_type_parameters=owner_has_type_parameters,
            )
            value_transformer = create_transformer(
                args[1],
                sync,
                runtime_package,
                owner_impl_type=owner_impl_type,
                owner_has_type_parameters=owner_has_type_parameters,
            )
            return DictTransformer(key_transformer, value_transformer)
        else:
            return IdentityTransformer(annotation)

    # Tuple[T1, T2, ...] or tuple[T, ...]
    if origin is tuple:
        if args:
            # Check if it's a variable-length tuple (tuple[T, ...])
            # In Python, this is represented as having Ellipsis in args
            if Ellipsis in args:
                # Variable-length tuple: tuple[T, ...]
                # The type T is before the Ellipsis
                item_transformer = create_transformer(args[0], sync, runtime_package, owner_impl_type=owner_impl_type)
                return TupleTransformer([item_transformer])
            else:
                # Fixed-size tuple: tuple[T1, T2, ...]
                # Create transformer for each element
                item_transformers = [
                    create_transformer(
                        arg,
                        sync,
                        runtime_package,
                        owner_impl_type=owner_impl_type,
                        owner_has_type_parameters=owner_has_type_parameters,
                    )
                    for arg in args
                ]
                return TupleTransformer(item_transformers)
        else:
            return IdentityTransformer(annotation)

    # Union types (including Optional[T])
    if origin is typing.Union:
        non_none_args = [arg for arg in args if arg is not type(None)]

        # Optional[T] case: Union[T, None]
        if len(non_none_args) == 1 and type(None) in args:
            inner_transformer = create_transformer(
                non_none_args[0],
                sync,
                runtime_package,
                owner_impl_type=owner_impl_type,
                owner_has_type_parameters=owner_has_type_parameters,
            )
            return OptionalTransformer(inner_transformer)

        # General Union - for now, treat as identity if no wrapped types
        # Could implement UnionTransformer if needed in the future
        return IdentityTransformer(annotation)

    # Generator types
    import collections.abc

    if origin is collections.abc.Generator or origin is collections.abc.Iterator:
        if args:
            yield_transformer = create_transformer(
                args[0],
                sync,
                runtime_package,
                owner_impl_type=owner_impl_type,
                owner_has_type_parameters=owner_has_type_parameters,
            )
            return SyncGeneratorTransformer(yield_transformer)
        else:
            return IdentityTransformer(annotation)

    # AsyncIterator[T] - single type arg, no send type
    # Note: AsyncIterator is NOT the same as AsyncGenerator - iterators don't have asend()/aclose()
    if origin is collections.abc.AsyncIterator:
        if args:
            item_transformer = create_transformer(
                args[0],
                sync,
                runtime_package,
                owner_impl_type=owner_impl_type,
                owner_has_type_parameters=owner_has_type_parameters,
            )
            return AsyncIteratorTransformer(item_transformer, runtime_package)
        else:
            # Bare AsyncIterator with no type args
            return AsyncIteratorTransformer(IdentityTransformer(typing.Any), runtime_package)

    # AsyncIterable[T] - has __aiter__() that returns AsyncIterator[T]
    if origin is collections.abc.AsyncIterable:
        if args:
            item_transformer = create_transformer(
                args[0],
                sync,
                runtime_package,
                owner_impl_type=owner_impl_type,
                owner_has_type_parameters=owner_has_type_parameters,
            )
            return AsyncIterableTransformer(item_transformer, runtime_package)
        else:
            # Bare AsyncIterable with no type args
            return AsyncIterableTransformer(IdentityTransformer(typing.Any), runtime_package)

    # AsyncGenerator[T, Send] - two type args
    if origin is collections.abc.AsyncGenerator:
        if args:
            yield_transformer = create_transformer(
                args[0],
                sync,
                runtime_package,
                owner_impl_type=owner_impl_type,
                owner_has_type_parameters=owner_has_type_parameters,
            )
            # Extract send type if provided (usually None for AsyncGenerator[T, SendType])
            send_type_str = "None"
            if len(args) > 1:
                send_type_str = _format_annotation_str(args[1])
            return AsyncGeneratorTransformer(yield_transformer, send_type_str=send_type_str)
        else:
            return IdentityTransformer(annotation)

    # Coroutine[YieldType, SendType, ReturnType] - three type args, we want ReturnType
    if origin is collections.abc.Coroutine:
        if args and len(args) >= 3:
            return_transformer = create_transformer(
                args[2],
                sync,
                runtime_package,
                owner_impl_type=owner_impl_type,
                owner_has_type_parameters=owner_has_type_parameters,
            )
            return CoroutineTransformer(return_transformer)
        else:
            # No type args or incomplete, use identity transformer for return type
            return CoroutineTransformer(IdentityTransformer(typing.Any))

    # Awaitable[T] - one type arg
    if origin is collections.abc.Awaitable:
        if args:
            return_transformer = create_transformer(
                args[0],
                sync,
                runtime_package,
                owner_impl_type=owner_impl_type,
                owner_has_type_parameters=owner_has_type_parameters,
            )
            return AwaitableTransformer(return_transformer)
        else:
            # No type args, use identity transformer for return type
            return AwaitableTransformer(IdentityTransformer(typing.Any))

    # Fallback for unknown generic types
    return IdentityTransformer(annotation)


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
            if origin in (list, dict, tuple, set, frozenset):
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
