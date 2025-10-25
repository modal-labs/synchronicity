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


class TypeTransformer(ABC):
    """Base class for type transformers that handle type signatures and translation."""

    @abstractmethod
    def wrapped_type(self, synchronized_types: dict[type, tuple[str, str]], target_module: str) -> str:
        """Return the type signature string for generated wrapper code.

        Args:
            synchronized_types: Dict mapping implementation types to (target_module, wrapper_name)
            target_module: Current target module (for local vs cross-module refs)

        Returns:
            Type string like "Person", "list[str]", "foo.bar.Person"
        """
        pass

    @abstractmethod
    def unwrap_expr(self, synchronized_types: dict[type, tuple[str, str]], var_name: str) -> str:
        """Generate Python expression to unwrap from wrapper → impl.

        Args:
            synchronized_types: Dict mapping implementation types to (target_module, wrapper_name)
            var_name: Variable name to unwrap

        Returns:
            Expression string like "value._impl_instance" or "[x._impl_instance for x in value]"
        """
        pass

    @abstractmethod
    def wrap_expr(self, synchronized_types: dict[type, tuple[str, str]], target_module: str, var_name: str) -> str:
        """Generate Python expression to wrap from impl → wrapper.

        Args:
            synchronized_types: Dict mapping implementation types to (target_module, wrapper_name)
            target_module: Current target module (for local vs cross-module refs)
            var_name: Variable name to wrap

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


class IdentityTransformer(TypeTransformer):
    """Transformer for types that don't need translation (primitives, etc.)."""

    def __init__(self, annotation):
        self.annotation = annotation

    def wrapped_type(self, synchronized_types: dict[type, tuple[str, str]], target_module: str) -> str:
        """Format the type annotation as-is."""
        return _format_annotation_str(self.annotation)

    def unwrap_expr(self, synchronized_types: dict[type, tuple[str, str]], var_name: str) -> str:
        """No unwrapping needed - return variable as-is."""
        return var_name

    def wrap_expr(self, synchronized_types: dict[type, tuple[str, str]], target_module: str, var_name: str) -> str:
        """No wrapping needed - return variable as-is."""
        return var_name

    def needs_translation(self) -> bool:
        return False


class WrappedClassTransformer(TypeTransformer):
    """Transformer for wrapped class types."""

    def __init__(self, impl_type: type):
        self.impl_type = impl_type

    def wrapped_type(self, synchronized_types: dict[type, tuple[str, str]], target_module: str) -> str:
        """Return the wrapper class name (local or fully qualified)."""
        if self.impl_type not in synchronized_types:
            # Should not happen if create_transformer is used correctly
            return _format_annotation_str(self.impl_type)

        wrapper_target_module, wrapper_name = synchronized_types[self.impl_type]

        if wrapper_target_module == target_module:
            # Local reference
            return wrapper_name
        else:
            # Cross-module reference
            return f"{wrapper_target_module}.{wrapper_name}"

    def unwrap_expr(self, synchronized_types: dict[type, tuple[str, str]], var_name: str) -> str:
        """Unwrap by accessing _impl_instance."""
        return f"{var_name}._impl_instance"

    def wrap_expr(self, synchronized_types: dict[type, tuple[str, str]], target_module: str, var_name: str) -> str:
        """Wrap by calling WrapperClass._from_impl()."""
        if self.impl_type not in synchronized_types:
            return var_name

        wrapper_target_module, wrapper_name = synchronized_types[self.impl_type]

        if wrapper_target_module == target_module:
            # Local reference
            return f"{wrapper_name}._from_impl({var_name})"
        else:
            # Cross-module reference
            return f"{wrapper_target_module}.{wrapper_name}._from_impl({var_name})"

    def needs_translation(self) -> bool:
        return True


class ListTransformer(TypeTransformer):
    """Transformer for list[T] types."""

    def __init__(self, item_transformer: TypeTransformer):
        self.item_transformer = item_transformer

    def wrapped_type(self, synchronized_types: dict[type, tuple[str, str]], target_module: str) -> str:
        """Return list[WrappedItemType]."""
        item_type_str = self.item_transformer.wrapped_type(synchronized_types, target_module)
        return f"list[{item_type_str}]"

    def unwrap_expr(self, synchronized_types: dict[type, tuple[str, str]], var_name: str) -> str:
        """Generate list comprehension to unwrap items."""
        if not self.item_transformer.needs_translation():
            return var_name

        item_unwrap = self.item_transformer.unwrap_expr(synchronized_types, "x")
        return f"[{item_unwrap} for x in {var_name}]"

    def wrap_expr(self, synchronized_types: dict[type, tuple[str, str]], target_module: str, var_name: str) -> str:
        """Generate list comprehension to wrap items."""
        if not self.item_transformer.needs_translation():
            return var_name

        item_wrap = self.item_transformer.wrap_expr(synchronized_types, target_module, "x")
        return f"[{item_wrap} for x in {var_name}]"

    def needs_translation(self) -> bool:
        return self.item_transformer.needs_translation()


class DictTransformer(TypeTransformer):
    """Transformer for dict[K, V] types."""

    def __init__(self, key_transformer: TypeTransformer, value_transformer: TypeTransformer):
        self.key_transformer = key_transformer
        self.value_transformer = value_transformer

    def wrapped_type(self, synchronized_types: dict[type, tuple[str, str]], target_module: str) -> str:
        """Return dict[WrappedKeyType, WrappedValueType]."""
        key_type_str = self.key_transformer.wrapped_type(synchronized_types, target_module)
        value_type_str = self.value_transformer.wrapped_type(synchronized_types, target_module)
        return f"dict[{key_type_str}, {value_type_str}]"

    def unwrap_expr(self, synchronized_types: dict[type, tuple[str, str]], var_name: str) -> str:
        """Generate dict comprehension to unwrap values."""
        if not self.value_transformer.needs_translation():
            return var_name

        value_unwrap = self.value_transformer.unwrap_expr(synchronized_types, "v")
        return f"{{k: {value_unwrap} for k, v in {var_name}.items()}}"

    def wrap_expr(self, synchronized_types: dict[type, tuple[str, str]], target_module: str, var_name: str) -> str:
        """Generate dict comprehension to wrap values."""
        if not self.value_transformer.needs_translation():
            return var_name

        value_wrap = self.value_transformer.wrap_expr(synchronized_types, target_module, "v")
        return f"{{k: {value_wrap} for k, v in {var_name}.items()}}"

    def needs_translation(self) -> bool:
        return self.value_transformer.needs_translation()


class TupleTransformer(TypeTransformer):
    """Transformer for tuple types - both fixed-size tuple[T1, T2] and variable-length tuple[T, ...]."""

    def __init__(self, item_transformers: list[TypeTransformer]):
        """
        Args:
            item_transformers: List of transformers for each tuple element.
                               If all elements are the same type, this can be a single-item list.
        """
        self.item_transformers = item_transformers

    def wrapped_type(self, synchronized_types: dict[type, tuple[str, str]], target_module: str) -> str:
        """Return tuple[WrappedType1, WrappedType2, ...] or tuple[WrappedType, ...]."""
        if len(self.item_transformers) == 1:
            # Variable-length tuple: tuple[T, ...]
            item_type_str = self.item_transformers[0].wrapped_type(synchronized_types, target_module)
            return f"tuple[{item_type_str}, ...]"
        else:
            # Fixed-size tuple: tuple[T1, T2, ...]
            item_type_strs = [t.wrapped_type(synchronized_types, target_module) for t in self.item_transformers]
            return f"tuple[{', '.join(item_type_strs)}]"

    def unwrap_expr(self, synchronized_types: dict[type, tuple[str, str]], var_name: str) -> str:
        """Generate tuple comprehension/constructor to unwrap items."""
        if not self.needs_translation():
            return var_name

        if len(self.item_transformers) == 1:
            # Variable-length tuple
            item_unwrap = self.item_transformers[0].unwrap_expr(synchronized_types, "x")
            return f"tuple({item_unwrap} for x in {var_name})"
        else:
            # Fixed-size tuple - unwrap each element by index
            unwrap_exprs = [
                t.unwrap_expr(synchronized_types, f"{var_name}[{i}]") for i, t in enumerate(self.item_transformers)
            ]
            return f"({', '.join(unwrap_exprs)})"

    def wrap_expr(self, synchronized_types: dict[type, tuple[str, str]], target_module: str, var_name: str) -> str:
        """Generate tuple comprehension/constructor to wrap items."""
        if not self.needs_translation():
            return var_name

        if len(self.item_transformers) == 1:
            # Variable-length tuple
            item_wrap = self.item_transformers[0].wrap_expr(synchronized_types, target_module, "x")
            return f"tuple({item_wrap} for x in {var_name})"
        else:
            # Fixed-size tuple - wrap each element by index
            wrap_exprs = [
                t.wrap_expr(synchronized_types, target_module, f"{var_name}[{i}]")
                for i, t in enumerate(self.item_transformers)
            ]
            return f"({', '.join(wrap_exprs)})"

    def needs_translation(self) -> bool:
        return any(t.needs_translation() for t in self.item_transformers)


class OptionalTransformer(TypeTransformer):
    """Transformer for Optional[T] (Union[T, None]) types."""

    def __init__(self, inner_transformer: TypeTransformer):
        self.inner_transformer = inner_transformer

    def wrapped_type(self, synchronized_types: dict[type, tuple[str, str]], target_module: str) -> str:
        """Return typing.Union[WrappedInnerType, None]."""
        inner_type_str = self.inner_transformer.wrapped_type(synchronized_types, target_module)
        return f"typing.Union[{inner_type_str}, None]"

    def unwrap_expr(self, synchronized_types: dict[type, tuple[str, str]], var_name: str) -> str:
        """Generate conditional expression to unwrap if not None."""
        if not self.inner_transformer.needs_translation():
            return var_name

        inner_unwrap = self.inner_transformer.unwrap_expr(synchronized_types, var_name)
        return f"{inner_unwrap} if {var_name} is not None else None"

    def wrap_expr(self, synchronized_types: dict[type, tuple[str, str]], target_module: str, var_name: str) -> str:
        """Generate conditional expression to wrap if not None."""
        if not self.inner_transformer.needs_translation():
            return var_name

        inner_wrap = self.inner_transformer.wrap_expr(synchronized_types, target_module, var_name)
        return f"{inner_wrap} if {var_name} is not None else None"

    def needs_translation(self) -> bool:
        return self.inner_transformer.needs_translation()


class GeneratorTransformer(TypeTransformer):
    """Transformer for Generator/AsyncGenerator types."""

    def __init__(self, yield_transformer: TypeTransformer, is_async: bool, send_type_str: str | None = "None"):
        self.yield_transformer = yield_transformer
        self.is_async = is_async
        self.send_type_str = send_type_str

    def wrapped_type(self, synchronized_types: dict[type, tuple[str, str]], target_module: str) -> str:
        """Return typing.Generator[WrappedYieldType, None, None] or typing.AsyncGenerator[...]."""
        yield_type_str = self.yield_transformer.wrapped_type(synchronized_types, target_module)

        if self.is_async:
            # If send_type_str is None, omit it (for AsyncIterator)
            if self.send_type_str is None:
                return f"typing.AsyncGenerator[{yield_type_str}]"
            else:
                return f"typing.AsyncGenerator[{yield_type_str}, {self.send_type_str}]"
        else:
            return f"typing.Generator[{yield_type_str}, None, None]"

    def unwrap_expr(self, synchronized_types: dict[type, tuple[str, str]], var_name: str) -> str:
        """Generators don't unwrap at the parameter level."""
        return var_name

    def wrap_expr(self, synchronized_types: dict[type, tuple[str, str]], target_module: str, var_name: str) -> str:
        """Generators don't wrap at the return level - wrapping happens per-yield."""
        return var_name

    def needs_translation(self) -> bool:
        """Generators need special handling but not standard translation."""
        return self.yield_transformer.needs_translation()

    def get_yield_wrap_expr(
        self, synchronized_types: dict[type, tuple[str, str]], target_module: str, var_name: str
    ) -> str:
        """Get the wrap expression for each yielded item."""
        return self.yield_transformer.wrap_expr(synchronized_types, target_module, var_name)


def create_transformer(annotation, synchronized_types: dict[type, tuple[str, str]]) -> TypeTransformer:
    """Create a transformer from a type annotation.

    Args:
        annotation: Type annotation (resolved with eval_str=True)
        synchronized_types: Dict mapping implementation types to (target_module, wrapper_name)

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
    if isinstance(annotation, type) and annotation in synchronized_types:
        return WrappedClassTransformer(annotation)

    # Check for generic types
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is None:
        # Non-generic type (primitive or non-wrapped class)
        return IdentityTransformer(annotation)

    # List[T]
    if origin is list:
        if args:
            item_transformer = create_transformer(args[0], synchronized_types)
            return ListTransformer(item_transformer)
        else:
            return IdentityTransformer(annotation)

    # Dict[K, V]
    if origin is dict:
        if len(args) >= 2:
            key_transformer = create_transformer(args[0], synchronized_types)
            value_transformer = create_transformer(args[1], synchronized_types)
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
                item_transformer = create_transformer(args[0], synchronized_types)
                return TupleTransformer([item_transformer])
            else:
                # Fixed-size tuple: tuple[T1, T2, ...]
                # Create transformer for each element
                item_transformers = [create_transformer(arg, synchronized_types) for arg in args]
                return TupleTransformer(item_transformers)
        else:
            return IdentityTransformer(annotation)

    # Union types (including Optional[T])
    if origin is typing.Union:
        non_none_args = [arg for arg in args if arg is not type(None)]

        # Optional[T] case: Union[T, None]
        if len(non_none_args) == 1 and type(None) in args:
            inner_transformer = create_transformer(non_none_args[0], synchronized_types)
            return OptionalTransformer(inner_transformer)

        # General Union - for now, treat as identity if no wrapped types
        # Could implement UnionTransformer if needed in the future
        return IdentityTransformer(annotation)

    # Generator types
    import collections.abc

    if origin is collections.abc.Generator or origin is collections.abc.Iterator:
        if args:
            yield_transformer = create_transformer(args[0], synchronized_types)
            return GeneratorTransformer(yield_transformer, is_async=False)
        else:
            return IdentityTransformer(annotation)

    # AsyncIterator[T] - single type arg, no send type
    if origin is collections.abc.AsyncIterator:
        if args:
            yield_transformer = create_transformer(args[0], synchronized_types)
            # AsyncIterator has no send type in the annotation, omit it from output
            return GeneratorTransformer(yield_transformer, is_async=True, send_type_str=None)
        else:
            return IdentityTransformer(annotation)

    # AsyncGenerator[T, Send] - two type args
    if origin is collections.abc.AsyncGenerator:
        if args:
            yield_transformer = create_transformer(args[0], synchronized_types)
            # Extract send type if provided (usually None for AsyncGenerator[T, SendType])
            send_type_str = "None"
            if len(args) > 1:
                send_type_str = _format_annotation_str(args[1])
            return GeneratorTransformer(yield_transformer, is_async=True, send_type_str=send_type_str)
        else:
            return IdentityTransformer(annotation)

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
