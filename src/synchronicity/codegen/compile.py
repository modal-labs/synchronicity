"""Main compilation module for generating wrapper code using TypeTransformers."""

from __future__ import annotations

import inspect
import types
import typing
from typing import TYPE_CHECKING

from synchronicity.module import Module

from .signature_utils import is_async_generator
from .type_transformer import create_transformer

if TYPE_CHECKING:
    pass


def _extract_typevars_from_annotation(annotation, collected: dict[str, typing.TypeVar | typing.ParamSpec]) -> None:
    """Recursively extract TypeVar and ParamSpec instances from a type annotation.

    Args:
        annotation: Type annotation to extract from
        collected: Dict to store found typevars (name -> typevar instance)
    """
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
    """Extract all TypeVar and ParamSpec instances used in a function's signature.

    Args:
        f: The function to extract from
        annotations: Resolved annotations dict from inspect.get_annotations

    Returns:
        Dict mapping typevar name to typevar instance
    """
    collected: dict[str, typing.TypeVar | typing.ParamSpec] = {}

    # Extract from all parameter annotations
    sig = inspect.signature(f)
    for param_name, param in sig.parameters.items():
        param_annotation = annotations.get(param_name, param.annotation)
        if param_annotation != inspect.Signature.empty:
            _extract_typevars_from_annotation(param_annotation, collected)

    # Extract from return annotation
    return_annotation = annotations.get("return", sig.return_annotation)
    if return_annotation != inspect.Signature.empty:
        _extract_typevars_from_annotation(return_annotation, collected)

    return collected


def _translate_typevar_bound(
    bound: type | str, synchronized_types: dict[type, tuple[str, str]], target_module: str
) -> str:
    """Translate a TypeVar bound to the wrapper type if it's a wrapped class.

    Args:
        bound: The bound value (can be a type, string, ForwardRef, or None)
        synchronized_types: Dict mapping implementation types to (target_module, wrapper_name)
        target_module: Current target module for local vs cross-module refs

    Returns:
        String representation of the bound for code generation
    """
    # Handle ForwardRef objects (from string annotations)
    if hasattr(bound, "__forward_arg__"):
        # Extract the string from the ForwardRef
        forward_str = bound.__forward_arg__  # type: ignore
        # Try to find if this string matches any wrapped class name
        for impl_type, (wrapper_target_module, wrapper_name) in synchronized_types.items():
            if impl_type.__name__ == forward_str:
                # Translate to wrapper name, always use string for forward compatibility
                if wrapper_target_module == target_module:
                    return f'"{wrapper_name}"'
                else:
                    return f'"{wrapper_target_module}.{wrapper_name}"'
        # Not a wrapped class, return as-is
        return f'"{forward_str}"'

    # Handle string forward references
    if isinstance(bound, str):
        # Try to find if this string matches any wrapped class name
        for impl_type, (wrapper_target_module, wrapper_name) in synchronized_types.items():
            if impl_type.__name__ == bound:
                # Translate to wrapper name
                if wrapper_target_module == target_module:
                    return wrapper_name
                else:
                    return f"{wrapper_target_module}.{wrapper_name}"
        # Not a wrapped class, return as-is
        return f'"{bound}"'

    # Handle direct type references
    if isinstance(bound, type):
        if bound in synchronized_types:
            # For wrapped classes, always use string forward reference
            # since the class may not be defined yet when TypeVar is declared
            wrapper_target_module, wrapper_name = synchronized_types[bound]
            if wrapper_target_module == target_module:
                return f'"{wrapper_name}"'
            else:
                return f'"{wrapper_target_module}.{wrapper_name}"'
        # Not a wrapped class, return qualified name (not quoted since it should be imported)
        return f"{bound.__module__}.{bound.__name__}" if bound.__module__ != "builtins" else bound.__name__

    # For other types, use repr
    return repr(bound)


def _generate_typevar_definitions(
    typevars: dict[str, typing.TypeVar | typing.ParamSpec],
    synchronized_types: dict[type, tuple[str, str]],
    target_module: str,
) -> list[str]:
    """Generate Python code to recreate TypeVar and ParamSpec definitions.

    Args:
        typevars: Dict mapping typevar name to typevar instance
        synchronized_types: Dict mapping implementation types to (target_module, wrapper_name)
        target_module: Current target module for translating bounds

    Returns:
        List of definition strings like 'T = typing.TypeVar("T", bound=SomeClass)'
    """
    definitions = []

    for name, typevar in typevars.items():
        if isinstance(typevar, typing.ParamSpec):
            # ParamSpec is simpler - just name
            definitions.append(f'{name} = typing.ParamSpec("{name}")')
        elif isinstance(typevar, typing.TypeVar):
            # TypeVar can have bounds, constraints, and variance
            args = [f'"{name}"']

            # Handle constraints (e.g., TypeVar('T', int, str))
            if hasattr(typevar, "__constraints__") and typevar.__constraints__:
                for constraint in typevar.__constraints__:
                    if isinstance(constraint, type):
                        if constraint in synchronized_types:
                            wrapper_target_module, wrapper_name = synchronized_types[constraint]
                            if wrapper_target_module == target_module:
                                args.append(wrapper_name)
                            else:
                                args.append(f"{wrapper_target_module}.{wrapper_name}")
                        else:
                            constraint_name = (
                                f"{constraint.__module__}.{constraint.__name__}"
                                if constraint.__module__ != "builtins"
                                else constraint.__name__
                            )
                            args.append(constraint_name)
                    else:
                        args.append(repr(constraint))

            # Handle bound (e.g., TypeVar('T', bound=SomeClass))
            if hasattr(typevar, "__bound__") and typevar.__bound__ is not None:
                bound_str = _translate_typevar_bound(typevar.__bound__, synchronized_types, target_module)
                args.append(f"bound={bound_str}")

            # Handle covariant/contravariant
            if hasattr(typevar, "__covariant__") and typevar.__covariant__:
                args.append("covariant=True")
            if hasattr(typevar, "__contravariant__") and typevar.__contravariant__:
                args.append("contravariant=True")

            definitions.append(f"{name} = typing.TypeVar({', '.join(args)})")

    return definitions


def _parse_parameters_with_transformers(
    sig: inspect.Signature,
    annotations: dict,
    synchronized_types: dict[type, tuple[str, str]],
    synchronizer_name: str,
    current_target_module: str,
    skip_self: bool = False,
    unwrap_indent: str = "    ",
) -> tuple[str, str, str]:
    """
    Parse function/method parameters using transformers.

    Args:
        sig: Function signature
        annotations: Resolved annotations dict from inspect.get_annotations
        synchronizer: The Synchronizer instance
        current_target_module: Current target module for type translation
        skip_self: Whether to skip 'self' parameter (for methods)
        unwrap_indent: Indentation for unwrap statements

    Returns:
        Tuple of (param_str, call_args_str, unwrap_code)
    """
    params = []
    call_args = []
    unwrap_stmts = []
    seen_positional_only = False
    seen_var_positional = False

    for name, param in sig.parameters.items():
        if skip_self and name == "self":
            continue

        # Check if we need to insert positional-only marker (/)
        if not seen_positional_only and param.kind != inspect.Parameter.POSITIONAL_ONLY:
            # We've transitioned past positional-only params
            if any(p.kind == inspect.Parameter.POSITIONAL_ONLY for p in sig.parameters.values()):
                # There were positional-only params before this one
                params.append("/")
            seen_positional_only = True

        # Get resolved annotation for this parameter
        param_annotation = annotations.get(name, param.annotation)

        # Create transformer for this parameter
        transformer = create_transformer(param_annotation, synchronized_types)

        # Build parameter declaration based on parameter kind
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            # Handle *args
            seen_var_positional = True
            if param_annotation != param.empty:
                wrapper_type_str = transformer.wrapped_type(synchronized_types, current_target_module)
                param_str = f"*{name}: {wrapper_type_str}"
            else:
                param_str = f"*{name}"

            # For call args, use unpacking
            if transformer.needs_translation():
                unwrap_expr = transformer.unwrap_expr(synchronized_types, name)
                unwrap_stmts.append(f"{unwrap_indent}{name}_impl = {unwrap_expr}")
                call_args.append(f"*{name}_impl")
            else:
                call_args.append(f"*{name}")

        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            # Handle **kwargs
            if param_annotation != param.empty:
                wrapper_type_str = transformer.wrapped_type(synchronized_types, current_target_module)
                param_str = f"**{name}: {wrapper_type_str}"
            else:
                param_str = f"**{name}"

            # For call args, use unpacking
            if transformer.needs_translation():
                unwrap_expr = transformer.unwrap_expr(synchronized_types, name)
                unwrap_stmts.append(f"{unwrap_indent}{name}_impl = {unwrap_expr}")
                call_args.append(f"**{name}_impl")
            else:
                call_args.append(f"**{name}")

        elif param.kind == inspect.Parameter.KEYWORD_ONLY:
            # Handle keyword-only parameters
            # If we haven't seen *args, insert bare * marker
            if not seen_var_positional:
                params.append("*")
                seen_var_positional = True

            # Build parameter declaration
            if param_annotation != param.empty:
                wrapper_type_str = transformer.wrapped_type(synchronized_types, current_target_module)
                param_str = f"{name}: {wrapper_type_str}"
            else:
                param_str = name

            # Handle default values
            if param.default is not param.empty:
                default_val = repr(param.default)
                param_str += f" = {default_val}"

            # For call args, use keyword syntax
            if transformer.needs_translation():
                unwrap_expr = transformer.unwrap_expr(synchronized_types, name)
                unwrap_stmts.append(f"{unwrap_indent}{name}_impl = {unwrap_expr}")
                call_args.append(f"{name}={name}_impl")
            else:
                call_args.append(f"{name}={name}")

        else:
            # Handle regular parameters (POSITIONAL_ONLY, POSITIONAL_OR_KEYWORD)
            if param_annotation != param.empty:
                wrapper_type_str = transformer.wrapped_type(synchronized_types, current_target_module)
                param_str = f"{name}: {wrapper_type_str}"

                # Generate unwrap code if needed
                if transformer.needs_translation():
                    unwrap_expr = transformer.unwrap_expr(synchronized_types, name)
                    unwrap_stmts.append(f"{unwrap_indent}{name}_impl = {unwrap_expr}")
                    call_args.append(f"{name}_impl")
                else:
                    call_args.append(name)
            else:
                param_str = name
                call_args.append(name)

            # Handle default values
            if param.default is not param.empty:
                default_val = repr(param.default)
                param_str += f" = {default_val}"

        params.append(param_str)

    param_str = ", ".join(params)
    call_args_str = ", ".join(call_args)
    unwrap_code = "\n".join(unwrap_stmts) if unwrap_stmts else ""

    return param_str, call_args_str, unwrap_code


def _build_call_with_wrap(
    call_expr: str,
    return_transformer,
    synchronized_types: dict[type, tuple[str, str]],
    synchronizer_name: str,
    current_target_module: str,
    indent: str = "    ",
    is_async: bool = True,
) -> str:
    """
    Build a function call with optional return value wrapping.

    This is used for non-generator return types. Nested generators inside
    return values (e.g., tuple[AsyncGenerator, ...]) are properly wrapped
    according to the is_async context.

    Args:
        call_expr: The function call expression
        return_transformer: TypeTransformer for the return type
        synchronized_types: Dict mapping implementation types to (target_module, wrapper_name)
        synchronizer_name: Name of the synchronizer
        current_target_module: Current target module
        indent: Indentation string
        is_async: Whether this is an async context (affects generator wrapping)

    Returns:
        Code string with the call and optional wrapping
    """
    if return_transformer.needs_translation():
        wrap_expr = return_transformer.wrap_expr(synchronized_types, current_target_module, "result", is_async=is_async)
        return f"""{indent}result = {call_expr}
{indent}return {wrap_expr}"""
    else:
        return f"{indent}return {call_expr}"


def _format_return_annotation(
    return_transformer,
    synchronized_types: dict[type, tuple[str, str]],
    synchronizer_name: str,
    current_target_module: str,
) -> tuple[str, str]:
    """
    Format return type annotations for both sync and async versions.

    Args:
        return_transformer: TypeTransformer for the return type
        synchronizer: The Synchronizer instance
        current_target_module: Current target module

    Returns:
        Tuple of (sync_return_str, async_return_str) with " -> " prefix
    """
    # Get the wrapped types for both sync and async contexts
    sync_return_type = return_transformer.wrapped_type(synchronized_types, current_target_module, is_async=False)
    async_return_type = return_transformer.wrapped_type(synchronized_types, current_target_module, is_async=True)

    if not sync_return_type:
        return "", ""

    # Quote the entire type annotation if it contains wrapped types
    should_quote = return_transformer.needs_translation()
    if should_quote:
        sync_return_str = f' -> "{sync_return_type}"'
        async_return_str = f' -> "{async_return_type}"'
    else:
        sync_return_str = f" -> {sync_return_type}"
        async_return_str = f" -> {async_return_type}"

    return sync_return_str, async_return_str


def compile_function(
    f: types.FunctionType,
    target_module: str,
    synchronizer_name: str,
    synchronized_types: dict[type, tuple[str, str]],
    *,
    globals_dict: dict[str, typing.Any] | None = None,
) -> str:
    """
    Compile a function into a wrapper class that provides both sync and async versions.

    Args:
        f: The function to compile
        target_module: Target module where this function will be generated
        synchronizer_name: Name of the synchronizer for async operations
        synchronized_types: Dict mapping impl types to (target_module, wrapper_name)
        globals_dict: Optional globals dict for resolving forward references

    Returns:
        String containing the generated wrapper class and decorated function code
    """
    origin_module = f.__module__
    current_target_module = target_module

    # Resolve all type annotations
    annotations = inspect.get_annotations(f, eval_str=True, globals=globals_dict)

    # Get function signature
    sig = inspect.signature(f)
    return_annotation = annotations.get("return", sig.return_annotation)

    # Create transformer for return type
    return_transformer = create_transformer(return_annotation, synchronized_types)

    # Parse parameters using transformers
    param_str, call_args_str, unwrap_code = _parse_parameters_with_transformers(
        sig,
        annotations,
        synchronized_types,
        synchronizer_name,
        current_target_module,
        skip_self=False,
        unwrap_indent="    ",
    )

    # Check if it's an async generator
    is_async_gen = is_async_generator(f, return_annotation)

    # Check if it's an async function
    is_async_func = inspect.iscoroutinefunction(f) or is_async_gen

    # For non-async functions, generate simple wrapper without @wrapped_function decorator
    if not is_async_func:
        # Format return type annotation (only need sync version)
        sync_return_str, _ = _format_return_annotation(
            return_transformer, synchronized_types, synchronizer_name, current_target_module
        )

        # Build function body with wrapping (sync context, so is_async=False)
        function_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            synchronized_types,
            synchronizer_name,
            current_target_module,
            indent="    ",
            is_async=False,
        )

        # Add impl_function reference and unwrap statements
        impl_ref = f"    impl_function = {origin_module}.{f.__name__}"
        if unwrap_code:
            function_body = f"{impl_ref}\n{unwrap_code}\n{function_body}"
        else:
            function_body = f"{impl_ref}\n{function_body}"

        # Generate simple function (no decorator, no wrapper class)
        return f"""def {f.__name__}({param_str}){sync_return_str}:
{function_body}"""

    # Format return types with translation
    sync_return_str, async_return_str = _format_return_annotation(
        return_transformer, synchronized_types, synchronizer_name, current_target_module
    )

    # Generate the wrapper class
    wrapper_class_name = f"_{f.__name__}"

    # Collect inline helper functions needed by return type
    inline_helpers_dict = return_transformer.get_wrapper_helpers(
        synchronized_types, current_target_module, synchronizer_name, indent="    "
    )
    helpers_code = "\n".join(inline_helpers_dict.values()) if inline_helpers_dict else ""

    # Build both sync and async bodies
    if is_async_gen:
        # For async generators, manually iterate with asend() to support two-way generators
        # Wrap in try/finally to ensure proper cleanup on aclose()
        wrap_expr = return_transformer.wrap_expr(synchronized_types, current_target_module, "gen")
        aio_body = (
            f"        gen = impl_function({call_args_str})\n"
            f"        _wrapped = {wrap_expr}\n"
            f"        _sent = None\n"
            f"        try:\n"
            f"            while True:\n"
            f"                try:\n"
            f"                    _item = await _wrapped.asend(_sent)\n"
            f"                    _sent = yield _item\n"
            f"                except StopAsyncIteration:\n"
            f"                    break\n"
            f"        finally:\n"
            f"            await _wrapped.aclose()"
        )

        # For sync version, use yield from for efficiency
        sync_wrap_expr = return_transformer.wrap_expr(synchronized_types, current_target_module, "gen", is_async=False)
        sync_function_body = f"    gen = impl_function({call_args_str})\n    yield from {sync_wrap_expr}"
    elif is_async_func:
        # For regular async functions
        aio_runner = f"get_synchronizer('{synchronizer_name}')._run_function_async"
        aio_body = _build_call_with_wrap(
            f"await {aio_runner}(impl_function({call_args_str}))",
            return_transformer,
            synchronized_types,
            synchronizer_name,
            current_target_module,
            indent="        ",
            is_async=True,
        )
        sync_runner = f"get_synchronizer('{synchronizer_name}')._run_function_sync"
        sync_function_body = _build_call_with_wrap(
            f"{sync_runner}(impl_function({call_args_str}))",
            return_transformer,
            synchronized_types,
            synchronizer_name,
            current_target_module,
            indent="    ",
            is_async=False,
        )
    else:
        # For non-async functions (shouldn't reach here)
        aio_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            synchronized_types,
            synchronizer_name,
            current_target_module,
            indent="        ",
            is_async=True,
        )
        sync_function_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            synchronized_types,
            synchronizer_name,
            current_target_module,
            indent="    ",
            is_async=False,
        )

    # Build unwrap section for aio() if needed
    aio_impl_ref = f"        impl_function = {origin_module}.{f.__name__}"
    aio_unwrap = f"\n{aio_impl_ref}"
    if unwrap_code:
        # Adjust indentation for aio method (8 spaces)
        aio_unwrap_lines = [line.replace("    ", "        ", 1) for line in unwrap_code.split("\n")]
        aio_unwrap += "\n" + "\n".join(aio_unwrap_lines)

    # Generate wrapper class with both __call__ (sync) and aio (async) methods
    # This preserves full signatures including parameter names for type checkers

    # Build unwrap section for __call__ (sync) if needed
    call_impl_ref = f"        impl_function = {origin_module}.{f.__name__}"
    call_unwrap = f"\n{call_impl_ref}"
    if unwrap_code:
        # Adjust indentation for __call__ method (8 spaces)
        call_unwrap_lines = [line.replace("    ", "        ", 1) for line in unwrap_code.split("\n")]
        call_unwrap += "\n" + "\n".join(call_unwrap_lines)

    # Adjust sync_function_body indentation (was 4 spaces, now needs 8 for __call__)
    sync_body_indented = "\n".join("    " + line if line.strip() else line for line in sync_function_body.split("\n"))

    # Build wrapper class with inline helpers at the top
    helpers_section = f"\n{helpers_code}\n" if helpers_code else ""

    wrapper_class_code = f"""class {wrapper_class_name}:{helpers_section}
    def __call__(self, {param_str}){sync_return_str}:{call_unwrap}
{sync_body_indented}

    async def aio(self, {param_str}){async_return_str}:{aio_unwrap}
{aio_body}
"""

    # Create instance of wrapper class
    wrapper_instance_name = f"_{f.__name__}_instance"
    instance_creation = f"{wrapper_instance_name} = {wrapper_class_name}()"

    # Generate dummy function with full signature for type checkers and go-to-definition
    # The @replace_with decorator swaps this with the actual wrapper instance
    dummy_function_code = f"""@replace_with({wrapper_instance_name})
def {f.__name__}({param_str}){sync_return_str}:
    # Dummy function for type checkers and IDE navigation
    # Actual implementation is in {wrapper_class_name}.__call__
    return {wrapper_instance_name}({", ".join(sig.parameters.keys())})"""

    return f"{wrapper_class_code}\n{instance_creation}\n\n{dummy_function_code}"


def compile_method_wrapper(
    method: types.FunctionType,
    method_name: str,
    synchronizer_name: str,
    synchronized_types: dict[type, tuple[str, str]],
    origin_module: str,
    class_name: str,
    current_target_module: str,
    *,
    globals_dict: dict[str, typing.Any] | None = None,
    generic_typevars: dict[str, typing.TypeVar | typing.ParamSpec] | None = None,
) -> tuple[str, str]:
    """
    Compile a method wrapper class that provides both sync and async versions.

    Args:
        method: The method to wrap
        method_name: The name of the method
        synchronizer_name: Name of the synchronizer for async operations
        synchronized_types: Dict mapping impl types to (target_module, wrapper_name)
        origin_module: The module where the original class is defined
        class_name: The name of the class containing the method
        current_target_module: The target module for the wrapper
        globals_dict: Optional globals dict for resolving forward references
        generic_typevars: TypeVars/ParamSpecs from parent class's Generic base (if any)

    Returns:
        Tuple of (wrapper_class_code, sync_method_code)
    """
    # Resolve all type annotations
    annotations = inspect.get_annotations(method, eval_str=True, globals=globals_dict)

    # Get method signature
    sig = inspect.signature(method)
    return_annotation = annotations.get("return", sig.return_annotation)

    # Create transformer for return type
    return_transformer = create_transformer(return_annotation, synchronized_types)

    # Parse parameters using transformers (skip 'self' for methods)
    param_str, call_args_str, unwrap_code = _parse_parameters_with_transformers(
        sig,
        annotations,
        synchronized_types,
        synchronizer_name,
        current_target_module,
        skip_self=True,
        unwrap_indent="        ",
    )

    # Check if it's an async generator
    is_async_gen = is_async_generator(method, return_annotation)

    # Check if it's async
    is_async = inspect.iscoroutinefunction(method) or is_async_gen

    # If not async at all, return empty strings (no wrapper needed)
    if not is_async:
        return "", ""

    # Format return types
    sync_return_str, async_return_str = _format_return_annotation(
        return_transformer, synchronized_types, synchronizer_name, current_target_module
    )

    # Generate the wrapper class
    wrapper_class_name = f"{class_name}_{method_name}"

    # Collect inline helper functions needed by return type
    inline_helpers_dict = return_transformer.get_wrapper_helpers(
        synchronized_types, current_target_module, synchronizer_name, indent="    "
    )
    helpers_code = "\n".join(inline_helpers_dict.values()) if inline_helpers_dict else ""

    # Build both sync and async bodies
    if is_async_gen:
        # For async generator methods, manually iterate with asend() to support two-way generators
        # Wrap in try/finally to ensure proper cleanup on aclose()
        gen_call = f"impl_method(self._wrapper_instance._impl_instance, {call_args_str})"
        wrap_expr = return_transformer.wrap_expr(synchronized_types, current_target_module, "gen")
        aio_body = (
            f"        gen = {gen_call}\n"
            f"        _wrapped = {wrap_expr}\n"
            f"        _sent = None\n"
            f"        try:\n"
            f"            while True:\n"
            f"                try:\n"
            f"                    _item = await _wrapped.asend(_sent)\n"
            f"                    _sent = yield _item\n"
            f"                except StopAsyncIteration:\n"
            f"                    break\n"
            f"        finally:\n"
            f"            await _wrapped.aclose()"
        )

        # For sync version, use yield from for efficiency
        sync_wrap_expr = return_transformer.wrap_expr(synchronized_types, current_target_module, "gen", is_async=False)
        sync_method_body = f"        gen = {gen_call}\n        yield from {sync_wrap_expr}"
    else:
        # For regular async methods
        aio_call_expr = (
            f"await self._wrapper_instance._synchronizer._run_function_async("
            f"impl_method(self._wrapper_instance._impl_instance, {call_args_str}))"
        )
        aio_body = _build_call_with_wrap(
            aio_call_expr,
            return_transformer,
            synchronized_types,
            synchronizer_name,
            current_target_module,
            indent="        ",
            is_async=True,
        )
        sync_call_expr = (
            f"self._wrapper_instance._synchronizer._run_function_sync("
            f"impl_method(self._wrapper_instance._impl_instance, {call_args_str}))"
        )
        sync_method_body = _build_call_with_wrap(
            sync_call_expr,
            return_transformer,
            synchronized_types,
            synchronizer_name,
            current_target_module,
            indent="        ",
            is_async=False,
        )

    # Build unwrap section for __call__() if needed
    sync_impl_ref = f"        impl_method = {origin_module}.{class_name}.{method_name}"
    sync_unwrap = f"\n{sync_impl_ref}"
    if unwrap_code:
        sync_unwrap += "\n" + unwrap_code

    # Build unwrap section for aio() if needed
    aio_impl_ref = f"        impl_method = {origin_module}.{class_name}.{method_name}"
    aio_unwrap = f"\n{aio_impl_ref}"
    if unwrap_code:
        aio_unwrap += "\n" + unwrap_code

    # The sync_method_body is already indented with 8 spaces, just use it directly
    # Simple __init__ just stores wrapper_instance
    # Build wrapper class with inline helpers after __init__
    helpers_section = f"\n{helpers_code}\n" if helpers_code else ""

    # Build Generic base for method wrapper if parent class is generic
    generic_typevars = generic_typevars or {}
    wrapper_generic_base = ""
    if generic_typevars:
        typevar_names = list(generic_typevars.keys())
        wrapper_generic_base = f"(typing.Generic[{', '.join(typevar_names)}])"
        wrapper_instance_type = f'"{class_name}[{", ".join(typevar_names)}]"'
    else:
        # Always quote the type to avoid forward reference issues
        wrapper_instance_type = f'"{class_name}"'

    wrapper_class_code = f"""class {wrapper_class_name}{wrapper_generic_base}:
    def __init__(self, wrapper_instance: {wrapper_instance_type}):
        self._wrapper_instance = wrapper_instance
{helpers_section}
    def __call__(self, {param_str}){sync_return_str}:{sync_unwrap}
{sync_method_body}

    async def aio(self, {param_str}){async_return_str}:{aio_unwrap}
{aio_body}
"""

    # Extract parameter names (excluding 'self') for the call, with proper varargs handling
    param_call_parts = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            param_call_parts.append(f"*{name}")
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            param_call_parts.append(f"**{name}")
        elif param.kind == inspect.Parameter.KEYWORD_ONLY:
            param_call_parts.append(f"{name}={name}")
        else:
            param_call_parts.append(name)
    param_call = ", ".join(param_call_parts)

    # Build parameterized wrapper class name for @wrapped_method decorator
    wrapper_class_ref = wrapper_class_name
    if generic_typevars:
        typevar_names = list(generic_typevars.keys())
        wrapper_class_ref = f"{wrapper_class_name}[{', '.join(typevar_names)}]"

    # Generate dummy method with descriptor that calls through to wrapper
    sync_method_code = f"""    @wrapped_method({wrapper_class_ref})
    def {method_name}(self, {param_str}){sync_return_str}:
        # Dummy method for type checkers and IDE navigation
        # Actual implementation is in {wrapper_class_name}.__call__
        return self.{method_name}.__call__({param_call})"""

    return wrapper_class_code, sync_method_code


def compile_class(
    cls: type,
    target_module: str,
    synchronizer_name: str,
    synchronized_types: dict[type, tuple[str, str]],
    *,
    globals_dict: dict[str, typing.Any] | None = None,
) -> str:
    """
    Compile a class into a wrapper class where all methods are wrapped.

    Args:
        cls: The class to compile
        target_module: Target module where this class will be generated
        synchronizer_name: Name of the synchronizer for async operations
        synchronized_types: Dict mapping impl types to (target_module, wrapper_name)
        globals_dict: Optional globals dict for resolving forward references

    Returns:
        String containing the generated wrapper class code
    """
    origin_module = cls.__module__
    current_target_module = target_module

    # Detect wrapped base classes for inheritance and Generic base
    wrapped_bases = []
    generic_base = None
    generic_typevars = {}  # Collect TypeVars from Generic base

    # Use __orig_bases__ to preserve Generic type parameters
    bases_to_check = getattr(cls, "__orig_bases__", cls.__bases__)

    for base in bases_to_check:
        # Check for typing.Generic base
        origin = typing.get_origin(base)
        # Generic classes have __origin__ set to typing.Generic
        if origin is not None and origin.__name__ == "Generic":
            # This is Generic[T, P, ...] - extract the TypeVars
            args = typing.get_args(base)
            if args:
                # Collect TypeVars from Generic parameters
                for arg in args:
                    if isinstance(arg, typing.TypeVar) or isinstance(arg, typing.ParamSpec):
                        generic_typevars[arg.__name__] = arg

                # Format Generic base with TypeVar names
                typevar_names = [arg.__name__ for arg in args if isinstance(arg, (typing.TypeVar, typing.ParamSpec))]
                if typevar_names:
                    generic_base = f"typing.Generic[{', '.join(typevar_names)}]"
        # Check for wrapped base classes (use actual __bases__ for this since we need real types)
        elif base is not object and base in synchronized_types:
            base_target_module, base_wrapper_name = synchronized_types[base]
            if base_target_module == current_target_module:
                wrapped_bases.append(base_wrapper_name)
            else:
                wrapped_bases.append(f"{base_target_module}.{base_wrapper_name}")

    # Get only methods defined in THIS class (not inherited)
    methods = []
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if not name.startswith("_") and name in cls.__dict__:
            methods.append((name, method))

    # Get only attributes defined in THIS class (not inherited)
    attributes = []
    # Use cls.__annotations__ directly to get only this class's annotations
    class_annotations = cls.__annotations__ if hasattr(cls, "__annotations__") else {}
    for name, annotation in class_annotations.items():
        if not name.startswith("_"):
            # Resolve forward references using inspect
            annotations_resolved = inspect.get_annotations(cls, eval_str=True, globals=globals_dict)
            resolved_annotation = annotations_resolved.get(name, annotation)
            transformer = create_transformer(resolved_annotation, synchronized_types)
            attr_type = transformer.wrapped_type(synchronized_types, current_target_module)
            attributes.append((name, attr_type))

    # Generate method wrapper classes and method code
    method_wrapper_classes = []
    method_definitions = []

    for method_name, method in methods:
        wrapper_class_code, sync_method_code = compile_method_wrapper(
            method,
            method_name,
            synchronizer_name,
            synchronized_types,
            origin_module,
            cls.__name__,
            current_target_module,
            globals_dict=globals_dict,
            generic_typevars=generic_typevars if generic_typevars else None,
        )
        if wrapper_class_code:
            method_wrapper_classes.append(wrapper_class_code)
        method_definitions.append(sync_method_code)

    # Get __init__ signature
    init_method = getattr(cls, "__init__", None)
    if init_method and init_method is not object.__init__:
        sig = inspect.signature(init_method)
        init_annotations = inspect.get_annotations(init_method, eval_str=True, globals=globals_dict)

        # Parse parameters (skip self)
        init_params = []
        init_call_args = []
        for name, param in sig.parameters.items():
            if name == "self":
                continue

            # Build parameter with type annotation if available
            param_annotation = init_annotations.get(name, param.annotation)
            if param_annotation != param.empty:
                transformer = create_transformer(param_annotation, synchronized_types)
                type_str = transformer.wrapped_type(synchronized_types, current_target_module)
                param_str = f"{name}: {type_str}"
            else:
                param_str = name

            # Add default value if present
            if param.default is not param.empty:
                default_val = repr(param.default)
                param_str += f" = {default_val}"

            init_params.append(param_str)
            init_call_args.append(f"{name}={name}")

        init_signature = ", ".join(init_params)
        init_call = ", ".join(init_call_args)
    else:
        init_signature = "*args, **kwargs"
        init_call = "*args, **kwargs"

    # Generate property definitions for attributes
    property_definitions = []
    for attr_name, attr_type in attributes:
        if attr_type:
            property_code = f"""    # Generated properties
    @property
    def {attr_name}(self) -> {attr_type}:
        return self._impl_instance.{attr_name}

    @{attr_name}.setter
    def {attr_name}(self, value: {attr_type}):
        self._impl_instance.{attr_name} = value"""
        else:
            property_code = f"""    @property
    def {attr_name}(self):
        return self._impl_instance.{attr_name}

    @{attr_name}.setter
    def {attr_name}(self, value):
        self._impl_instance.{attr_name} = value"""
        property_definitions.append(property_code)

    # Generate the wrapper class
    properties_section = "\n\n".join(property_definitions) if property_definitions else ""
    methods_section = "\n\n".join(method_definitions) if method_definitions else ""

    # Generate _from_impl classmethod (only for root classes without wrapped bases)
    if not wrapped_bases:
        from_impl_method = f"""    @classmethod
    def _from_impl(cls, impl_instance: {origin_module}.{cls.__name__}) -> "{cls.__name__}":
        \"\"\"Create wrapper from implementation instance, preserving identity via cache.\"\"\"
        # Use id() as cache key since impl instances are Python objects
        cache_key = id(impl_instance)

        # Check cache first
        if cache_key in cls._instance_cache:
            return cls._instance_cache[cache_key]

        # Create new wrapper using __new__ to bypass __init__
        wrapper = cls.__new__(cls)
        wrapper._impl_instance = impl_instance

        # Cache it
        cls._instance_cache[cache_key] = wrapper

        return wrapper"""
    else:
        # Derived classes inherit _from_impl from base
        from_impl_method = ""

    # Generate class declaration with inheritance (including Generic if present)
    all_bases = []
    if wrapped_bases:
        all_bases.extend(wrapped_bases)
    if generic_base:
        all_bases.append(generic_base)

    if all_bases:
        bases_str = ", ".join(all_bases)
        class_declaration = f"""class {cls.__name__}({bases_str}):"""
    else:
        class_declaration = f"""class {cls.__name__}:"""

    # Generate class attributes (only for root classes without wrapped bases)
    if not wrapped_bases:
        class_attrs = (
            f"""    \"\"\"Wrapper class for {origin_module}.{cls.__name__} """
            f"""with sync/async method support\"\"\"

    _synchronizer = get_synchronizer('{synchronizer_name}')
    _instance_cache: weakref.WeakValueDictionary = weakref.WeakValueDictionary()"""
        )
    else:
        class_attrs = (
            f"""    \"\"\"Wrapper class for {origin_module}.{cls.__name__} with sync/async method support\"\"\""""
        )

    # Generate __init__ method (call super if there are wrapped bases)
    if wrapped_bases:
        init_method = f"""    def __init__(self, {init_signature}):
        super().__init__({init_call})
        # Update to more specific derived type
        self._impl_instance = {origin_module}.{cls.__name__}({init_call})"""
    else:
        init_method = f"""    def __init__(self, {init_signature}):
        self._impl_instance = {origin_module}.{cls.__name__}({init_call})"""

    wrapper_class_code = f"""{class_declaration}
{class_attrs}

{init_method}

{from_impl_method}

{properties_section}

{methods_section}"""

    # Combine all the code
    all_code = []
    all_code.extend(method_wrapper_classes)
    all_code.append("")  # Add blank line before main class
    all_code.append(wrapper_class_code)

    return "\n".join(all_code)


def _get_cross_module_imports(
    module_name: str,
    module_items: dict,
    synchronized_types: dict[type, tuple[str, str]],
) -> dict[str, set[str]]:
    """
    Detect which wrapped classes from other modules are referenced in this module.

    Args:
        module_name: The current module being compiled
        module_items: Items in the current module
        synchronizer: The Synchronizer instance

    Returns:
        Dict mapping target module names to sets of wrapper class names
    """
    cross_module_refs = {}  # target_module -> set of class names

    # Check each item in this module for references to wrapped classes from other modules
    for obj in module_items.keys():
        # Get signature if it's a function or class with methods
        if isinstance(obj, types.FunctionType):
            annotations = inspect.get_annotations(obj, eval_str=True)
            for annotation in annotations.values():
                _check_annotation_for_cross_refs(annotation, module_name, synchronized_types, cross_module_refs)
        elif isinstance(obj, type):
            # Check methods of the class
            for method_name, method in inspect.getmembers(obj, predicate=inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                annotations = inspect.get_annotations(method, eval_str=True)
                for annotation in annotations.values():
                    _check_annotation_for_cross_refs(annotation, module_name, synchronized_types, cross_module_refs)

    return cross_module_refs


def _check_annotation_for_cross_refs(
    annotation,
    current_module: str,
    synchronized_types: dict[type, tuple[str, str]],
    cross_module_refs: dict,
) -> None:
    """Check a type annotation for references to wrapped classes from other modules."""
    # Handle direct class references
    if isinstance(annotation, type) and annotation in synchronized_types:
        target_module, wrapper_name = synchronized_types[annotation]
        if target_module != current_module:
            if target_module not in cross_module_refs:
                cross_module_refs[target_module] = set()
            cross_module_refs[target_module].add(wrapper_name)

    # Handle generic types
    import typing

    args = typing.get_args(annotation)
    if args:
        for arg in args:
            _check_annotation_for_cross_refs(arg, current_module, synchronized_types, cross_module_refs)


def compile_module(
    module: Module,
    synchronized_types: dict[type, tuple[str, str]],
    synchronizer_name: str,
) -> str:
    """
    Compile wrapped items for a single target module.

    Args:
        module_name: The target module name to generate
        synchronizer: The Synchronizer instance

    Returns:
        String containing compiled wrapper code for this module
    """

    # Collect unique implementation modules
    impl_modules = set()
    for o, (target_module, target_name) in module.module_items().items():
        impl_modules.add(o.__module__)

    # Check if there are any wrapped classes (for weakref import)
    has_wrapped_classes = len(module._registered_classes) > 0

    # Detect cross-module references
    cross_module_imports = _get_cross_module_imports(module.target_module, module.module_items(), synchronized_types)

    # Generate header with imports
    imports = "\n".join(f"import {mod}" for mod in sorted(impl_modules))

    # Generate cross-module imports
    cross_module_import_strs = []
    for target_module in sorted(cross_module_imports.keys()):
        cross_module_import_strs.append(f"import {target_module}")

    cross_module_imports_str = "\n".join(cross_module_import_strs) if cross_module_import_strs else ""

    header = f"""import typing

{imports}

from synchronicity.descriptor import replace_with, wrapped_method
from synchronicity.synchronizer import get_synchronizer
"""

    if cross_module_imports_str:
        header += f"\n{cross_module_imports_str}\n"

    compiled_code = [header]

    # Generate weakref import if there are wrapped classes
    if has_wrapped_classes:
        compiled_code.append("import weakref")
        compiled_code.append("")  # Add blank line

    # Separate classes and functions for correct ordering
    classes = []
    functions = []

    for o, (target_module, target_name) in module.module_items().items():
        if isinstance(o, type):
            classes.append(o)
        elif isinstance(o, types.FunctionType):
            functions.append(o)

    # Collect all TypeVars and ParamSpecs used in functions and class methods
    module_typevars: dict[str, typing.TypeVar | typing.ParamSpec] = {}

    # Extract from standalone functions
    for func in functions:
        annotations = inspect.get_annotations(func, eval_str=True)
        func_typevars = _extract_typevars_from_function(func, annotations)
        module_typevars.update(func_typevars)

    # Extract from class methods
    for cls in classes:
        # Extract TypeVars from Generic base class if present (use __orig_bases__)
        bases_to_check = getattr(cls, "__orig_bases__", cls.__bases__)
        for base in bases_to_check:
            origin = typing.get_origin(base)
            if origin is not None and hasattr(origin, "__name__") and origin.__name__ == "Generic":
                args = typing.get_args(base)
                for arg in args:
                    if isinstance(arg, typing.TypeVar) or isinstance(arg, typing.ParamSpec):
                        module_typevars[arg.__name__] = arg

        # Extract TypeVars from method signatures
        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not name.startswith("_"):
                annotations = inspect.get_annotations(method, eval_str=True)
                method_typevars = _extract_typevars_from_function(method, annotations)
                module_typevars.update(method_typevars)

    # Generate typevar definitions if any were found
    if module_typevars:
        typevar_defs = _generate_typevar_definitions(module_typevars, synchronized_types, module.target_module)
        compiled_code.append("# TypeVar and ParamSpec definitions")
        for definition in typevar_defs:
            compiled_code.append(definition)
        compiled_code.append("")  # Add blank line

    # Compile all classes first
    for cls in classes:
        code = compile_class(cls, module.target_module, synchronizer_name, synchronized_types)
        compiled_code.append(code)

    # Then compile all functions
    for func in functions:
        code = compile_function(func, module.target_module, synchronizer_name, synchronized_types)
        compiled_code.append(code)
        compiled_code.append("")  # Add blank line

    return "\n".join(compiled_code)


def compile_modules(modules: list[Module], synchronizer_name: str) -> dict[str, str]:
    """
    Compile wrapped items into separate module files.

    Args:
        synchronizer: The Synchronizer instance

    Returns:
        Dict mapping module names to their generated code
    """
    synchronized_classes = {}
    for module in modules:
        synchronized_classes.update(module._registered_classes)

    # Compile each module
    result = {}
    for module in modules:
        code = compile_module(module, synchronized_classes, synchronizer_name)
        if code:
            result[module.target_module] = code

    return result
