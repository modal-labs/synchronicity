"""Utility functions for code generation."""

from __future__ import annotations

import collections.abc
import inspect
import sys
import types
import typing
import warnings

from .default_expressions import resolve_parameter_default_expressions
from .ir import MethodBindingKind, ParameterIR
from .signature_utils import is_async_generator
from .transformer_ir import (
    CallableTypeIR,
    DictTypeIR,
    ImplQualifiedRef,
    ListTypeIR,
    OptionalTypeIR,
    SelfTypeIR,
    SequenceTypeIR,
    SubscriptedWrappedClassTypeIR,
    TupleTypeIR,
    TypeTransformerIR,
    UnionTypeIR,
    WrappedClassTypeIR,
)
from .type_transformer import CallableTransformer, WrappedClassTransformer

if typing.TYPE_CHECKING:
    from .transformer_materialize import MaterializeContext


def _normalize_async_annotation(func, return_annotation):
    """
    Normalize async function annotations to Awaitable[T] for uniform handling.

    Converts `async def f() -> T` into `def f() -> Awaitable[T]` at the annotation level,
    allowing the type transformer system to handle async/sync generation uniformly.

    Args:
        func: The function or method object to check
        return_annotation: The return type annotation (may be inspect.Signature.empty)

    Returns:
        The normalized annotation (wrapped in Awaitable if async, otherwise unchanged)

    Note:
        Async generators are NOT wrapped in Awaitable - they remain as AsyncGenerator[T].
    """
    # Check if it's an async generator - these stay as-is
    # Async generators are special: they're defined with `async def` but they're NOT awaitable
    if is_async_generator(func, return_annotation):
        return return_annotation

    # Check if it's an async function (async def)
    if inspect.iscoroutinefunction(func):
        # Wrap in Awaitable[T]
        if return_annotation == inspect.Signature.empty:
            # No annotation -> Awaitable[Any]
            return collections.abc.Awaitable[typing.Any]
        else:
            # Has annotation T -> Awaitable[T]
            return collections.abc.Awaitable[return_annotation]

    # Already has explicit Awaitable/Coroutine, or is sync - return as-is
    return return_annotation


def _safe_get_annotations(obj, globals_dict=None):
    """
    Safely get annotations, with fallback for forward references under TYPE_CHECKING.

    For forward references that can't be resolved (NameError), we try to import the
    module from fully qualified names (e.g., "my_mod.SomeType").
    """
    try:
        return inspect.get_annotations(obj, eval_str=True, globals=globals_dict)
    except NameError:
        # Forward reference can't be resolved - try importing from qualified names
        # Get raw string annotations
        raw_annotations = inspect.get_annotations(obj, eval_str=False, globals=globals_dict)

        # Build an extended globals dict with imports for qualified names
        extended_globals = (globals_dict or {}).copy()

        for key, annotation_str in raw_annotations.items():
            if isinstance(annotation_str, str) and "." in annotation_str:
                # Extract module path from qualified name (e.g., "my_mod.sub.SomeType" -> "my_mod.sub")
                parts = annotation_str.split(".")
                if len(parts) >= 2:
                    # Import the full module path (all parts except the last, which is the class name)
                    module_path = ".".join(parts[:-1])
                    try:
                        # Try to import the module
                        import importlib

                        importlib.import_module(module_path)
                        # Add the top-level module to extended_globals
                        # For "a.b.c.Class", add "a" -> sys.modules["a"]
                        top_level_module = parts[0]
                        if top_level_module not in extended_globals:
                            extended_globals[top_level_module] = sys.modules.get(top_level_module)
                    except ImportError:
                        pass  # Skip if module can't be imported

        # Try again with extended globals
        try:
            return inspect.get_annotations(obj, eval_str=True, globals=extended_globals)
        except (NameError, AttributeError):
            # Still can't resolve - return string annotations
            return raw_annotations


def _contains_self_type(annotation) -> bool:
    """Check if a type annotation contains typing.Self.

    Args:
        annotation: Type annotation to check

    Returns:
        True if typing.Self is found anywhere in the annotation
    """
    # Check for typing.Self directly
    if annotation is typing.Self:
        return True

    # Check for generic types with typing.Self as an argument
    origin = typing.get_origin(annotation)
    if origin is not None:
        args = typing.get_args(annotation)
        for arg in args:
            if _contains_self_type(arg):
                return True

    return False


def _extract_typevars_from_annotation(annotation, collected: dict[str, typing.TypeVar | typing.ParamSpec]) -> None:
    """Recursively extract TypeVar and ParamSpec instances from a type annotation."""
    # Handle TypeVar and ParamSpec directly
    if isinstance(annotation, typing.TypeVar):
        collected[annotation.__name__] = annotation
        return
    if isinstance(annotation, typing.ParamSpec):
        collected[annotation.__name__] = annotation
        return

    # Recursively process generic types
    args = typing.get_args(annotation)

    if args:
        for arg in args:
            _extract_typevars_from_annotation(arg, collected)


def _extract_typevars_from_function(
    f: types.FunctionType, annotations: dict[str, typing.Any]
) -> dict[str, typing.TypeVar | typing.ParamSpec]:
    """Extract all TypeVar and ParamSpec instances used in a function's signature."""
    collected: dict[str, typing.TypeVar | typing.ParamSpec] = {}

    # Extract from all annotations (parameters and return type)
    for annotation in annotations.values():
        _extract_typevars_from_annotation(annotation, collected)

    return collected


def parse_parameters_to_ir(
    func: types.FunctionType,
    sig: inspect.Signature,
    annotations: dict,
    *,
    impl_module: types.ModuleType,
    skip_first_param: bool = False,
    owner_impl_type: type | None = None,
    owner_has_type_parameters: bool = False,
    impl_modules: frozenset[str] | None = None,
    source_label_prefix: str | None = None,
) -> tuple[ParameterIR, ...]:
    """Collect :class:`ParameterIR` from a signature (no emission strings)."""
    from .transformer_materialize import annotation_to_transformer_ir

    resolved_defaults = resolve_parameter_default_expressions(
        func,
        sig,
        impl_module=impl_module,
        source_label_prefix=source_label_prefix,
    )

    result: list[ParameterIR] = []
    for i, (name, param) in enumerate(sig.parameters.items()):
        if i == 0 and skip_first_param:
            continue

        param_annotation = annotations.get(name, param.annotation)
        if param_annotation is inspect.Signature.empty or param_annotation is param.empty:
            annotation_ir = None
        else:
            annotation_ir = annotation_to_transformer_ir(
                param_annotation,
                owner_impl_type=owner_impl_type,
                owner_has_type_parameters=owner_has_type_parameters,
                impl_modules=impl_modules,
                source_label=(f"{source_label_prefix} parameter {name!r}" if source_label_prefix is not None else None),
            )
            if isinstance(annotation_ir, CallableTypeIR) and _callable_ir_contains_wrapped_refs(annotation_ir):
                warnings.warn(
                    (
                        f"{source_label_prefix or func.__qualname__} parameter {name!r} is a callable containing "
                        "synchronized types. Callable-valued parameters are passed through unchanged at runtime, "
                        "so generated wrapper annotations use implementation types inside the callable signature."
                    ),
                    UserWarning,
                    stacklevel=2,
                )

        default_expr: str | None = None
        default_import_refs = ()
        if param.default is not inspect.Parameter.empty:
            resolved_default = resolved_defaults[name]
            default_expr = resolved_default.expression
            default_import_refs = resolved_default.import_refs

        result.append(
            ParameterIR(
                name=name,
                kind=int(param.kind),
                annotation_ir=annotation_ir,
                default_expr=default_expr,
                default_import_refs=default_import_refs,
            )
        )
    return tuple(result)


def _callable_ir_contains_wrapped_refs(ir: CallableTypeIR) -> bool:
    items: list[TypeTransformerIR] = [ir.return_type]
    if ir.params is not None:
        items.extend(ir.params)
    return any(_transformer_ir_contains_wrapped_refs(item) for item in items)


def _transformer_ir_contains_wrapped_refs(ir: TypeTransformerIR) -> bool:
    if isinstance(ir, (WrappedClassTypeIR, SubscriptedWrappedClassTypeIR, SelfTypeIR)):
        return True
    if isinstance(ir, ListTypeIR):
        return _transformer_ir_contains_wrapped_refs(ir.item)
    if isinstance(ir, SequenceTypeIR):
        return _transformer_ir_contains_wrapped_refs(ir.item)
    if isinstance(ir, OptionalTypeIR):
        return _transformer_ir_contains_wrapped_refs(ir.inner)
    if isinstance(ir, DictTypeIR):
        return _transformer_ir_contains_wrapped_refs(ir.key) or _transformer_ir_contains_wrapped_refs(ir.value)
    if isinstance(ir, TupleTypeIR):
        return any(_transformer_ir_contains_wrapped_refs(item) for item in ir.items)
    if isinstance(ir, UnionTypeIR):
        return any(_transformer_ir_contains_wrapped_refs(item) for item in ir.items)
    if isinstance(ir, CallableTypeIR):
        return _callable_ir_contains_wrapped_refs(ir)
    return False


def _parameter_annotation_str(transformer, current_target_module: str) -> str:
    if isinstance(transformer, CallableTransformer):
        return transformer.passthrough_annotation_type(current_target_module)
    return transformer.annotation_type(current_target_module)


def format_parameters_for_emit(
    parameters: tuple[ParameterIR, ...],
    current_target_module: str,
    runtime_package: str = "synchronicity2",
    unwrap_indent: str = "    ",
    *,
    mat_ctx: MaterializeContext | None = None,
) -> tuple[str, str, str]:
    """Build ``param_str``, ``call_args_str``, and unwrap lines from :class:`ParameterIR` (emitter-side)."""
    from .transformer_materialize import materialize_transformer_ir

    params: list[str] = []
    call_args: list[str] = []
    unwrap_stmts: list[str] = []

    last_positional_only_index = -1
    positional_only_marker_added = False

    def _vararg_unwrap_expr(transformer, source_name: str) -> str:
        item_unwrap = (
            transformer.unwrap_expr("_item", current_target_module)
            if isinstance(transformer, CallableTransformer)
            else transformer.unwrap_expr("_item")
        )
        return f"tuple({item_unwrap} for _item in {source_name})"

    def _varkw_unwrap_expr(transformer, source_name: str) -> str:
        value_unwrap = (
            transformer.unwrap_expr("_value", current_target_module)
            if isinstance(transformer, CallableTransformer)
            else transformer.unwrap_expr("_value")
        )
        return f"{{_key: {value_unwrap} for _key, _value in {source_name}.items()}}"

    for param_ir in parameters:
        name = param_ir.name
        kind = param_ir.kind
        transformer = (
            materialize_transformer_ir(param_ir.annotation_ir, runtime_package, ctx=mat_ctx)
            if param_ir.annotation_ir is not None
            else None
        )

        if kind == inspect.Parameter.POSITIONAL_ONLY:
            last_positional_only_index = len(params)

        if kind == inspect.Parameter.VAR_POSITIONAL:
            if param_ir.annotation_ir is not None:
                assert transformer is not None
                ann = _parameter_annotation_str(transformer, current_target_module)
                params.append(f"*{name}: {ann}")
                if transformer.needs_translation():
                    unwrap_expr = _vararg_unwrap_expr(transformer, name)
                    unwrap_stmts.append(f"{unwrap_indent}{name}_impl = {unwrap_expr}")
                    call_args.append(f"*{name}_impl")
                else:
                    call_args.append(f"*{name}")
            else:
                params.append(f"*{name}")
                call_args.append(f"*{name}")

        elif kind == inspect.Parameter.VAR_KEYWORD:
            if param_ir.annotation_ir is not None:
                assert transformer is not None
                ann = _parameter_annotation_str(transformer, current_target_module)
                params.append(f"**{name}: {ann}")
                if transformer.needs_translation():
                    unwrap_expr = _varkw_unwrap_expr(transformer, name)
                    unwrap_stmts.append(f"{unwrap_indent}{name}_impl = {unwrap_expr}")
                    call_args.append(f"**{name}_impl")
                else:
                    call_args.append(f"**{name}")
            else:
                params.append(f"**{name}")
                call_args.append(f"**{name}")

        elif kind == inspect.Parameter.KEYWORD_ONLY:
            if param_ir.annotation_ir is not None:
                assert transformer is not None
                ann = _parameter_annotation_str(transformer, current_target_module)
                param_str = f"{name}: {ann}"

                if transformer.needs_translation():
                    unwrap_expr = (
                        transformer.unwrap_expr(name, current_target_module)
                        if isinstance(transformer, CallableTransformer)
                        else transformer.unwrap_expr(name)
                    )
                    unwrap_stmts.append(f"{unwrap_indent}{name}_impl = {unwrap_expr}")
                    call_args.append(f"{name}={name}_impl")
                else:
                    call_args.append(f"{name}={name}")
            else:
                param_str = name
                call_args.append(f"{name}={name}")

            if param_ir.default_expr is not None:
                param_str += f" = {param_ir.default_expr}"

            params.append(param_str)

        else:
            if param_ir.annotation_ir is not None:
                assert transformer is not None
                ann = _parameter_annotation_str(transformer, current_target_module)
                param_str = f"{name}: {ann}"

                if transformer.needs_translation():
                    unwrap_expr = (
                        transformer.unwrap_expr(name, current_target_module)
                        if isinstance(transformer, CallableTransformer)
                        else transformer.unwrap_expr(name)
                    )
                    unwrap_stmts.append(f"{unwrap_indent}{name}_impl = {unwrap_expr}")
                    call_args.append(f"{name}_impl")
                else:
                    call_args.append(name)
            else:
                param_str = name
                call_args.append(name)

            if param_ir.default_expr is not None:
                param_str += f" = {param_ir.default_expr}"

            params.append(param_str)

        if not positional_only_marker_added and last_positional_only_index >= 0:
            if (
                kind != inspect.Parameter.POSITIONAL_ONLY
                and kind != inspect.Parameter.VAR_POSITIONAL
                and len(params) > last_positional_only_index
            ):
                params.insert(last_positional_only_index + 1, "/")
                positional_only_marker_added = True

    param_str = ", ".join(params)
    call_args_str = ", ".join(call_args)
    unwrap_code = "\n".join(unwrap_stmts) if unwrap_stmts else ""

    return param_str, call_args_str, unwrap_code


def _unwrap_to_self_transformer(transformer):
    """If the effective return type is ``typing.Self``, return ``SelfTransformer``; else ``None``."""
    from .type_transformer import AwaitableTransformer, CoroutineTransformer, SelfTransformer

    t = transformer
    while isinstance(t, (AwaitableTransformer, CoroutineTransformer)):
        t = t.return_transformer
    return t if isinstance(t, SelfTransformer) else None


def _effective_inner_transformer(transformer):
    from .type_transformer import AwaitableTransformer, CoroutineTransformer

    t = transformer
    while isinstance(t, (AwaitableTransformer, CoroutineTransformer)):
        t = t.return_transformer
    return t


def _build_call_with_wrap(
    call_expr: str,
    return_transformer,
    current_target_module: str,
    indent: str = "    ",
    is_async: bool = True,
    *,
    is_function: bool = False,
    method_type: MethodBindingKind | None = None,
    method_owner_impl_ref: ImplQualifiedRef | None = None,
) -> str:
    """Build a function call with optional return value wrapping."""
    from .type_transformer import (
        AsyncContextManagerTransformer,
        AwaitableTransformer,
        CoroutineTransformer,
    )

    def _adjust_method_helper_reference(expr: str) -> str:
        if not isinstance(return_transformer, AsyncContextManagerTransformer):
            return expr
        if method_type == MethodBindingKind.CLASSMETHOD:
            return expr.replace("self.", "cls.")
        if method_type == MethodBindingKind.STATICMETHOD and method_owner_impl_ref is not None:
            wrapper_name = method_owner_impl_ref.qualname.rpartition(".")[2]
            return expr.replace("self.", f"{wrapper_name}.")
        return expr

    def _wrap_result_expr(outer_transformer) -> str:
        st = _unwrap_to_self_transformer(outer_transformer)
        if st is not None and method_type is not None:
            return st.wrap_expr_for_method(
                current_target_module,
                "result",
                is_async=is_async,
                method_type=method_type,
            )
        inner = outer_transformer
        while isinstance(inner, (AwaitableTransformer, CoroutineTransformer)):
            inner = inner.return_transformer
        return inner.wrap_expr(current_target_module, "result", is_async=is_async)

    # Check if this is an awaitable type that needs synchronizer wrapping
    if isinstance(return_transformer, (AwaitableTransformer, CoroutineTransformer)):
        # Wrap the call with synchronizer to await/run it
        if is_async:
            wrapped_call = f"await _synchronizer._run_function_async({call_expr})"
        else:
            wrapped_call = f"_synchronizer._run_function_sync({call_expr})"

        inner_transformer = return_transformer.return_transformer
        if inner_transformer.needs_translation():
            eff = _effective_inner_transformer(return_transformer)
            if (
                method_type == MethodBindingKind.INSTANCE
                and not is_function
                and method_owner_impl_ref is not None
                and isinstance(eff, WrappedClassTransformer)
                and eff.impl_ref == method_owner_impl_ref
            ):
                wrap_expr = "self._from_impl(result)"
            else:
                wrap_expr = _wrap_result_expr(return_transformer)
            wrap_expr = _adjust_method_helper_reference(wrap_expr)
            if is_function:
                wrap_expr = wrap_expr.replace("self.", "")
            return f"""{indent}result = {wrapped_call}
{indent}return {wrap_expr}"""
        else:
            return f"{indent}return {wrapped_call}"

    # Regular wrapping for non-awaitable types
    if return_transformer.needs_translation():
        eff = _effective_inner_transformer(return_transformer)
        if (
            method_type == MethodBindingKind.INSTANCE
            and not is_function
            and method_owner_impl_ref is not None
            and isinstance(eff, WrappedClassTransformer)
            and eff.impl_ref == method_owner_impl_ref
        ):
            wrap_expr = "self._from_impl(result)"
        else:
            wrap_expr = _wrap_result_expr(return_transformer)
        wrap_expr = _adjust_method_helper_reference(wrap_expr)
        if is_function:
            wrap_expr = wrap_expr.replace("self.", "")
        return f"""{indent}result = {call_expr}
{indent}return {wrap_expr}"""
    else:
        return f"{indent}return {call_expr}"


def _format_return_annotation(
    return_transformer,
    current_target_module: str,
) -> tuple[str, str]:
    """Format return type annotations for both sync and async versions."""

    sync_return_type = return_transformer.annotation_type(current_target_module, is_async=False)
    async_return_type = return_transformer.annotation_type(current_target_module, is_async=True)

    if not sync_return_type:
        return "", ""

    sync_return_str = f" -> {sync_return_type}"
    async_return_str = f" -> {async_return_type}"

    return sync_return_str, async_return_str
