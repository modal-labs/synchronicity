"""Function wrapper code generation."""

from __future__ import annotations

import inspect
import types
import typing

from .compile_utils import (
    _build_call_with_wrap,
    _format_return_annotation,
    _normalize_async_annotation,
    _parse_parameters_with_transformers,
    _safe_get_annotations,
)
from .signature_utils import is_async_generator
from .type_transformer import (
    AsyncGeneratorTransformer,
    AsyncIteratorTransformer,
    create_transformer,
)


def compile_function(
    f: types.FunctionType,
    target_module: str,
    synchronized_types: dict[type, tuple[str, str]],
    *,
    globals_dict: dict[str, typing.Any] | None = None,
    runtime_package: str = "synchronicity",
) -> str:
    """
    Compile a function into a wrapper that provides both sync and async versions.

    Args:
        f: The function to compile
        target_module: Target module where this function will be generated
        synchronized_types: Dict mapping impl types to (target_module, wrapper_name)
        globals_dict: Optional globals dict for resolving forward references

    Returns:
        String containing the generated async wrapper function and decorated sync function
    """
    origin_module = f.__module__
    current_target_module = target_module

    # Resolve all type annotations (with fallback for TYPE_CHECKING imports)
    annotations = _safe_get_annotations(f, globals_dict)

    # Get function signature
    sig = inspect.signature(f)
    return_annotation = annotations.get("return", sig.return_annotation)

    # Normalize async def annotations to Awaitable[T] for uniform handling
    # Note: async generators are NOT wrapped in Awaitable
    return_annotation = _normalize_async_annotation(f, return_annotation)

    # Create transformer for return type
    return_transformer = create_transformer(return_annotation, synchronized_types, runtime_package)

    # Parse parameters using transformers
    param_str, call_args_str, unwrap_code = _parse_parameters_with_transformers(
        sig,
        annotations,
        synchronized_types,
        current_target_module,
        runtime_package,
        skip_first_param=False,
        unwrap_indent="    ",
    )

    # Check if it's an async generator
    # Note: After normalization, async generators are NOT wrapped in Awaitable
    is_async_gen = is_async_generator(f, return_annotation)

    # If it's actually a generator function, override the return transformer to use AsyncGeneratorTransformer
    # even if it's annotated as AsyncIterator (since AsyncGenerator is a subtype of AsyncIterator)
    if is_async_gen:
        if isinstance(return_transformer, AsyncIteratorTransformer):
            # Convert AsyncIteratorTransformer to AsyncGeneratorTransformer
            # since the function is actually a generator
            # Pass send_type_str=None (not "None") to omit the send type from the annotation
            return_transformer = AsyncGeneratorTransformer(return_transformer.item_transformer, send_type_str=None)

    # Import here to avoid circular imports
    from .type_transformer import AwaitableTransformer, CoroutineTransformer

    # Determine if this needs async/sync wrappers based on the transformer type
    # After normalization, async def functions have AwaitableTransformer
    needs_async_wrapper = is_async_gen or isinstance(return_transformer, (AwaitableTransformer, CoroutineTransformer))

    # For non-async functions, generate simple wrapper without @wrapped_function decorator
    if not needs_async_wrapper:
        # Format return type annotation (only need sync version)
        sync_return_str, _ = _format_return_annotation(return_transformer, synchronized_types, current_target_module)

        # Collect inline helper functions if return type needs translation (e.g., AsyncIterator)
        inline_helpers_dict = return_transformer.get_wrapper_helpers(
            synchronized_types, current_target_module, indent=""
        )
        # For module-level functions, we don't need @staticmethod decorators and use no indentation
        if inline_helpers_dict:
            # Remove @staticmethod decorator lines
            cleaned_helpers = {}
            for name, helper_code in inline_helpers_dict.items():
                lines = helper_code.split("\n")
                cleaned_lines = []
                for line in lines:
                    if line.strip().startswith("@staticmethod"):
                        continue
                    cleaned_lines.append(line)
                cleaned_helpers[name] = "\n".join(cleaned_lines)
            helpers_code = "\n".join(cleaned_helpers.values())
        else:
            helpers_code = ""

        # Build function body with wrapping (sync context, so is_async=False)
        function_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            synchronized_types,
            current_target_module,
            indent="    ",
            is_async=False,
            is_function=True,
        )

        # Add impl_function reference and unwrap statements
        impl_ref = f"    impl_function = {origin_module}.{f.__name__}"
        if unwrap_code:
            function_body = f"{impl_ref}\n{unwrap_code}\n{function_body}"
        else:
            function_body = f"{impl_ref}\n{function_body}"

        # Generate simple function (no decorator, no wrapper class) with helpers if needed
        function_code = f"""def {f.__name__}({param_str}){sync_return_str}:
{function_body}"""

        if helpers_code:
            return f"{helpers_code}\n\n{function_code}"
        else:
            return function_code

    # Format return types with translation
    sync_return_str, async_return_str = _format_return_annotation(
        return_transformer, synchronized_types, current_target_module
    )

    # Collect inline helper functions needed by return type
    # For functions (not methods), we need to strip @staticmethod decorators
    inline_helpers_dict = return_transformer.get_wrapper_helpers(
        synchronized_types, current_target_module, indent="    "
    )

    # For AwaitableTransformer/CoroutineTransformer, also collect helpers from the inner return type
    from .type_transformer import AwaitableTransformer, CoroutineTransformer

    if isinstance(return_transformer, (AwaitableTransformer, CoroutineTransformer)):
        inner_helpers = return_transformer.return_transformer.get_wrapper_helpers(
            synchronized_types, current_target_module, indent="    "
        )
        inline_helpers_dict.update(inner_helpers)
    # Strip @staticmethod decorators from helpers for module-level functions
    if inline_helpers_dict:
        # Remove @staticmethod and adjust indentation for module-level functions
        cleaned_helpers = {}
        for name, helper_code in inline_helpers_dict.items():
            # Remove @staticmethod decorator lines and reduce indentation by 4 spaces
            lines = helper_code.split("\n")
            cleaned_lines = []
            for line in lines:
                if line.strip().startswith("@staticmethod"):
                    continue
                # Reduce indentation by 4 spaces (was 4 for class method, now 0 for module-level)
                if line.startswith("    "):
                    cleaned_lines.append(line[4:])
                else:
                    cleaned_lines.append(line)
            cleaned_helpers[name] = "\n".join(cleaned_lines)
        helpers_code = "\n".join(cleaned_helpers.values())
    else:
        helpers_code = ""

    # Generate async wrapper function name (double underscore prefix pattern)
    aio_function_name = f"__{f.__name__}_aio"

    # Build async wrapper function body
    aio_impl_ref = f"    impl_function = {origin_module}.{f.__name__}"
    aio_unwrap_section = aio_impl_ref
    if unwrap_code:
        aio_unwrap_section += "\n" + unwrap_code

    if is_async_gen:
        # For async generators, manually iterate with asend() to support two-way generators
        # Wrap in try/finally to ensure proper cleanup on aclose()
        wrap_expr_raw = return_transformer.wrap_expr(synchronized_types, current_target_module, "gen")
        # For functions, remove self. prefix (helpers are module-level, not class methods)
        wrap_expr = wrap_expr_raw.replace("self.", "")
        aio_body = (
            f"    gen = impl_function({call_args_str})\n"
            f"    _wrapped = {wrap_expr}\n"
            f"    _sent = None\n"
            f"    try:\n"
            f"        while True:\n"
            f"            try:\n"
            f"                _item = await _wrapped.asend(_sent)\n"
            f"                _sent = yield _item\n"
            f"            except StopAsyncIteration:\n"
            f"                break\n"
            f"    finally:\n"
            f"        await _wrapped.aclose()"
        )
    else:
        # For functions returning Awaitable[T] (from normalized async def)
        # The _build_call_with_wrap will handle the synchronizer wrapping
        aio_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            synchronized_types,
            current_target_module,
            indent="    ",
            is_async=True,
            is_function=True,
        )

    # Generate async wrapper function
    async_wrapper_code = f"""async def {aio_function_name}({param_str}){async_return_str}:
{aio_unwrap_section}
{aio_body}
"""

    # Build sync function body
    sync_impl_ref = f"    impl_function = {origin_module}.{f.__name__}"
    sync_unwrap_section = sync_impl_ref
    if unwrap_code:
        sync_unwrap_section += "\n" + unwrap_code

    if is_async_gen:
        # For sync version of async generator, use yield from for efficiency
        sync_wrap_expr_raw = return_transformer.wrap_expr(
            synchronized_types, current_target_module, "gen", is_async=False
        )
        # For functions, remove self. prefix (helpers are module-level, not class methods)
        sync_wrap_expr = sync_wrap_expr_raw.replace("self.", "")
        sync_function_body = f"    gen = impl_function({call_args_str})\n    yield from {sync_wrap_expr}"
    else:
        # For functions returning Awaitable[T] (from normalized async def)
        # The _build_call_with_wrap will handle the synchronizer wrapping
        sync_function_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            synchronized_types,
            current_target_module,
            indent="    ",
            is_async=False,
            is_function=True,
        )

    # Generate sync function with @wrapped_function decorator
    sync_function_code = f"""@wrapped_function({aio_function_name})
def {f.__name__}({param_str}){sync_return_str}:
{sync_unwrap_section}
{sync_function_body}
"""

    # Combine helpers, async wrapper, and sync function
    if helpers_code:
        return f"{helpers_code}\n\n{async_wrapper_code}{sync_function_code}"
    else:
        return f"{async_wrapper_code}{sync_function_code}"
