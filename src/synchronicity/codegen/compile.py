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


def _replace_self_with_class(type_str: str, class_name: str, original_class_name: str | None = None) -> str:
    """Replace 'typing.Self' or wrapper class name with target type in a type string.

    Args:
        type_str: Type annotation string (may contain quoted or unquoted class names)
        class_name: Target class name to use (e.g., "OWNER_TYPE" or "ClassName[T, U]")
        original_class_name: Original class name to replace (e.g., "FunctionWrapper")

    Returns:
        Modified string with Self or class name replaced
    """
    # Replace typing.Self (unquoted)
    result = type_str.replace("typing.Self", class_name)
    result = result.replace("Self", class_name)

    # If original_class_name provided, replace quoted occurrences of it
    if original_class_name:
        # Replace quoted original class name with quoted target class name
        result = result.replace(f'"{original_class_name}"', f'"{class_name}"')

    return result


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
    skip_first_param: bool = False,
    unwrap_indent: str = "    ",
) -> tuple[str, str, str]:
    """
    Parse function/method parameters using transformers.

    Args:
        sig: Function signature
        annotations: Resolved annotations dict from inspect.get_annotations
        synchronizer: The Synchronizer instance
        current_target_module: Current target module for type translation
        skip_first_param: If True, skip the first parameter (for self/cls)
        unwrap_indent: Indentation for unwrap statements

    Returns:
        Tuple of (param_str, call_args_str, unwrap_code)
    """
    params = []
    call_args = []
    unwrap_stmts = []
    seen_positional_only = False
    seen_var_positional = False

    for i, (name, param) in enumerate(sig.parameters.items()):
        if skip_first_param and i == 0:
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
        skip_first_param=False,
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
    method_type: str = "instance",
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
        method_type: Type of method - "instance", "classmethod", or "staticmethod"
        globals_dict: Optional globals dict for resolving forward references
        generic_typevars: TypeVars/ParamSpecs from parent class's Generic base (if any)

    Returns:
        Tuple of (wrapper_functions_code, sync_method_code)
        - wrapper_functions_code: Generated wrapper functions
        - sync_method_code: The dummy method with descriptor decorator
    """
    # Resolve all type annotations
    annotations = inspect.get_annotations(method, eval_str=True, globals=globals_dict)

    # Get method signature
    sig = inspect.signature(method)
    return_annotation = annotations.get("return", sig.return_annotation)

    # Check if typing.Self is used in any annotation
    uses_self_type = _contains_self_type(return_annotation) or any(
        _contains_self_type(ann) for ann in annotations.values()
    )

    # Get the impl class from synchronized_types for Self resolution
    impl_class = None
    for cls_key, (mod, name) in synchronized_types.items():
        if mod == current_target_module and name == class_name:
            impl_class = cls_key
            break

    # Replace Self with the actual class for transformer creation
    transformer_annotation = return_annotation
    if uses_self_type and impl_class is not None:
        # Replace typing.Self with the actual impl class for proper wrapping
        if return_annotation is typing.Self:
            transformer_annotation = impl_class

    # Create transformer for return type
    return_transformer = create_transformer(transformer_annotation, synchronized_types)

    # Parse parameters using transformers
    # Skip first parameter for instance methods and classmethods (self/cls),
    # but not for staticmethods
    skip_first_param = method_type in ("instance", "classmethod")

    param_str, call_args_str, unwrap_code = _parse_parameters_with_transformers(
        sig,
        annotations,
        synchronized_types,
        synchronizer_name,
        current_target_module,
        skip_first_param=skip_first_param,
        unwrap_indent="        ",
    )

    # For the wrapper's __call__ method, param_str is correct (cls/self already skipped).
    # The dummy method signature matches the wrapper's __call__ signature exactly.
    # The descriptor's __get__ overload tells pyright what type is returned when accessing Class.method.
    # For classmethods, we add cls parameter to dummy signature to help type checking
    # (though it's not in the actual wrapper __call__, the descriptor handles binding correctly)
    dummy_param_str = param_str
    if method_type == "classmethod":
        if dummy_param_str:
            dummy_param_str = f'cls: type["{class_name}"], {dummy_param_str}'
        else:
            dummy_param_str = f'cls: type["{class_name}"]'

    # Replace typing.Self with OWNER_TYPE in parameter strings if used
    if uses_self_type:
        param_str = _replace_self_with_class(param_str, "OWNER_TYPE", class_name)

    # Check if it's an async generator
    is_async_gen = is_async_generator(method, return_annotation)

    # Check if it's async
    is_async = inspect.iscoroutinefunction(method) or is_async_gen

    # Format return types
    sync_return_str, async_return_str = _format_return_annotation(
        return_transformer, synchronized_types, synchronizer_name, current_target_module
    )

    # Replace typing.Self in return annotations
    # For async methods, use OWNER_TYPE (will be resolved by descriptor)
    # For sync-only methods, use actual class name (with type parameters if generic)
    if uses_self_type:
        # Build the actual class name with type parameters if it's generic
        actual_class_name = class_name
        if generic_typevars:
            typevar_names = list(generic_typevars.keys())
            actual_class_name = f"{class_name}[{', '.join(typevar_names)}]"

        # For sync-only methods (no async), use actual class name
        # For async methods, use OWNER_TYPE which will be resolved by the descriptor
        if is_async:
            # Async methods: use OWNER_TYPE (will be resolved via descriptor's generic)
            sync_return_str = _replace_self_with_class(sync_return_str, "OWNER_TYPE", class_name)
            async_return_str = _replace_self_with_class(async_return_str, "OWNER_TYPE", class_name)
        else:
            # Sync-only methods: use actual class name directly
            # _format_return_annotation already quotes the type if needs_translation()
            # Replace OWNER_TYPE inside the quoted string (between -> " and ")
            # Pattern: -> "OWNER_TYPE" -> -> "FunctionWrapper[P, R]"
            if ' -> "' in sync_return_str:
                # Extract the type part inside quotes
                start_idx = sync_return_str.find(' -> "') + 5
                end_idx = sync_return_str.rfind('"')
                if end_idx > start_idx:
                    quoted_type = sync_return_str[start_idx:end_idx]
                    # Replace OWNER_TYPE or class_name with actual_class_name (no extra quotes)
                    new_quoted_type = quoted_type.replace("OWNER_TYPE", actual_class_name).replace(
                        class_name, actual_class_name
                    )
                    sync_return_str = sync_return_str[:start_idx] + new_quoted_type + sync_return_str[end_idx:]
                else:
                    # Fallback: simple replace
                    sync_return_str = sync_return_str.replace("OWNER_TYPE", actual_class_name).replace(
                        class_name, actual_class_name
                    )
            else:
                # Not quoted, just replace
                sync_return_str = sync_return_str.replace("OWNER_TYPE", actual_class_name).replace(
                    class_name, actual_class_name
                )
            async_return_str = None  # Not used for sync-only

    # Generate the wrapper class
    wrapper_class_name = f"{class_name}_{method_name}"

    # Build the call expression based on method type
    # For instance methods, we need to reference wrapper_instance parameter
    # For classmethods/staticmethods, we'll handle differently
    if method_type == "instance":
        # For instance methods in wrapper functions, use wrapper_instance parameter
        call_expr_prefix = f"impl_method(wrapper_instance._impl_instance, {call_args_str})"
    elif method_type == "classmethod":
        # For classmethod wrapper functions, pass wrapper_class as cls (which becomes the impl class)
        # The call should reference the impl class directly
        impl_class_ref = f"{origin_module}.{class_name}"
        call_expr_prefix = f"{impl_class_ref}.{method_name}({call_args_str})"
    elif method_type == "staticmethod":
        # For staticmethod wrapper functions, call via the class (no bound instance)
        impl_class_ref = f"{origin_module}.{class_name}"
        call_expr_prefix = f"{impl_class_ref}.{method_name}({call_args_str})"
    else:
        # Fallback
        call_expr_prefix = f"impl_method(wrapper_instance._impl_instance, {call_args_str})"

    # Build both sync and async bodies (or just sync for non-async methods)
    # For instance methods, these will be wrapper functions
    # For classmethods/staticmethods, we'll handle separately
    # Initialize variables
    aio_body = None
    sync_method_body = ""

    if method_type == "instance":
        if not is_async:
            # For sync instance methods, just call directly without synchronizer
            sync_call_expr = call_expr_prefix
            sync_method_body = _build_call_with_wrap(
                sync_call_expr,
                return_transformer,
                synchronized_types,
                synchronizer_name,
                current_target_module,
                indent="    ",
                is_async=False,
            )
            # Add impl_method reference
            impl_method_line = f"    impl_method = {origin_module}.{class_name}.{method_name}"
            sync_method_body = impl_method_line + "\n" + sync_method_body
            aio_body = None  # No async version for sync methods
        elif is_async_gen:
            # For async generator instance methods
            gen_call = call_expr_prefix
            wrap_expr_raw = return_transformer.wrap_expr(synchronized_types, current_target_module, "gen")
            # Replace self with wrapper_instance for async wrapper function
            wrap_expr = wrap_expr_raw.replace("self.", "wrapper_instance.")
            impl_method_line = f"impl_method = {origin_module}.{class_name}.{method_name}"
            aio_body = (
                f"    {impl_method_line}\n"
                f"    gen = {gen_call}\n"
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
            # For sync version, use yield from for efficiency
            sync_wrap_expr_raw = return_transformer.wrap_expr(
                synchronized_types, current_target_module, "gen", is_async=False
            )
            # Replace self with self for sync method (will be replaced later when putting in method body)
            sync_wrap_expr = sync_wrap_expr_raw
            impl_method_line_sync = f"    {impl_method_line}"
            sync_method_body = f"{impl_method_line_sync}\n    gen = {gen_call}\n    yield from {sync_wrap_expr}"
        else:
            # For regular async instance methods - need synchronizer from wrapper_instance
            impl_method_line = f"    impl_method = {origin_module}.{class_name}.{method_name}"
            aio_call_expr = f"await wrapper_instance._synchronizer._run_function_async({call_expr_prefix})"
            sync_call_expr = f"wrapper_instance._synchronizer._run_function_sync({call_expr_prefix})"

            aio_body = _build_call_with_wrap(
                aio_call_expr,
                return_transformer,
                synchronized_types,
                synchronizer_name,
                current_target_module,
                indent="    ",
                is_async=True,
            )
            aio_body = impl_method_line + "\n" + aio_body
            sync_method_body = _build_call_with_wrap(
                sync_call_expr,
                return_transformer,
                synchronized_types,
                synchronizer_name,
                current_target_module,
                indent="    ",
                is_async=False,
            )
            sync_method_body = impl_method_line + "\n" + sync_method_body
    elif method_type == "classmethod":
        # For classmethod wrapper functions
        if not is_async:
            # Sync classmethod - just call directly
            sync_call_expr = call_expr_prefix
            sync_method_body = _build_call_with_wrap(
                sync_call_expr,
                return_transformer,
                synchronized_types,
                synchronizer_name,
                current_target_module,
                indent="    ",
                is_async=False,
            )
            aio_body = None
        elif is_async_gen:
            # Async generator classmethod
            gen_call = call_expr_prefix
            wrap_expr_raw = return_transformer.wrap_expr(synchronized_types, current_target_module, "gen")
            # Replace self with wrapper_class for async wrapper function
            wrap_expr = wrap_expr_raw.replace("self.", "wrapper_class.")
            aio_body = (
                f"    gen = {gen_call}\n"
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
            sync_wrap_expr_raw = return_transformer.wrap_expr(
                synchronized_types, current_target_module, "gen", is_async=False
            )
            # Will be replaced with cls when putting in method body
            sync_wrap_expr = sync_wrap_expr_raw
            sync_method_body = f"    gen = {gen_call}\n    yield from {sync_wrap_expr}"
        else:
            # Regular async classmethod - use wrapper_class._synchronizer
            aio_call_expr = f"await wrapper_class._synchronizer._run_function_async({call_expr_prefix})"
            sync_call_expr = f"wrapper_class._synchronizer._run_function_sync({call_expr_prefix})"

            aio_body = _build_call_with_wrap(
                aio_call_expr,
                return_transformer,
                synchronized_types,
                synchronizer_name,
                current_target_module,
                indent="    ",
                is_async=True,
            )
            sync_method_body = _build_call_with_wrap(
                sync_call_expr,
                return_transformer,
                synchronized_types,
                synchronizer_name,
                current_target_module,
                indent="    ",
                is_async=False,
            )
    elif method_type == "staticmethod":
        # For staticmethod wrapper functions
        if not is_async:
            # Sync staticmethod - just call directly
            sync_call_expr = call_expr_prefix
            sync_method_body = _build_call_with_wrap(
                sync_call_expr,
                return_transformer,
                synchronized_types,
                synchronizer_name,
                current_target_module,
                indent="    ",
                is_async=False,
            )
            aio_body = None
        elif is_async_gen:
            # Async generator staticmethod
            gen_call = call_expr_prefix
            wrap_expr_raw = return_transformer.wrap_expr(synchronized_types, current_target_module, "gen")
            # For staticmethods, helpers are instance methods but we don't have self
            # We need to create a temporary instance or access via class
            # For now, use the class name to access static helper - but helpers are instance methods
            # Actually, for staticmethods we might need to use a different pattern
            # Let's use the class to call as a bound method: {class_name}()._wrap_async_gen_...
            # Or better: access via a temporary instance
            # For now, replace self with a pattern that creates temp instance
            if "self." in wrap_expr_raw:
                # Extract helper name and create expression that uses class to create instance
                # Actually, simpler: use the class directly and create instance on the fly
                # Or even simpler: helpers should be accessible via the class itself if they're @staticmethod
                # But they're instance methods... Let's use {class_name}()._helper_name pattern
                wrap_expr = wrap_expr_raw.replace("self.", f"{class_name}()._").replace("_(", "(")
            else:
                wrap_expr = wrap_expr_raw
            aio_body = (
                f"    gen = {gen_call}\n"
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
            sync_wrap_expr_raw = return_transformer.wrap_expr(
                synchronized_types, current_target_module, "gen", is_async=False
            )
            # For sync staticmethod, replace self when putting in method body
            if "self." in sync_wrap_expr_raw:
                sync_wrap_expr = sync_wrap_expr_raw.replace("self.", f"{class_name}()._").replace("_(", "(")
            else:
                sync_wrap_expr = sync_wrap_expr_raw
            sync_method_body = f"    gen = {gen_call}\n    yield from {sync_wrap_expr}"
        else:
            # Regular async staticmethod - use get_synchronizer directly
            aio_call_expr = f"await get_synchronizer('{synchronizer_name}')._run_function_async({call_expr_prefix})"
            sync_call_expr = f"get_synchronizer('{synchronizer_name}')._run_function_sync({call_expr_prefix})"

            aio_body = _build_call_with_wrap(
                aio_call_expr,
                return_transformer,
                synchronized_types,
                synchronizer_name,
                current_target_module,
                indent="    ",
                is_async=True,
            )
            sync_method_body = _build_call_with_wrap(
                sync_call_expr,
                return_transformer,
                synchronized_types,
                synchronizer_name,
                current_target_module,
                indent="    ",
                is_async=False,
            )

    # Generate async wrapper methods inside the class (not module-level functions)
    # This allows them to use Self and class generics properly
    # Use __{method_name}_aio naming pattern (double underscore prefix)
    aio_method_name = f"__{method_name}_aio"

    if method_type == "instance":
        if aio_body is not None:
            # Async instance method: generate async method with self
            # Replace wrapper_instance with self in the body
            # aio_body is indented with 4 spaces, needs 8 spaces for method body
            aio_body_with_self = aio_body.replace("wrapper_instance", "self")
            aio_body_lines = aio_body_with_self.split("\n")
            # Add 4 more spaces to each line (8 total for method body)
            aio_body_indented = "\n".join("        " + line if line.strip() else "" for line in aio_body_lines)
            aio_wrapper_method = (
                f'    async def {aio_method_name}(self: "{class_name}", {param_str}){async_return_str}:\n'
                f"{aio_body_indented}"
            )
            wrapper_functions_code = aio_wrapper_method
        else:
            # Sync-only method: no async wrapper needed
            wrapper_functions_code = ""
            aio_body = None
    elif method_type == "classmethod":
        if aio_body is not None:
            # Async classmethod: generate async method with cls
            # Replace wrapper_class with cls in the body
            # aio_body is indented with 4 spaces, needs 8 spaces for method body
            aio_body_with_cls = aio_body.replace("wrapper_class", "cls")
            aio_body_lines = aio_body_with_cls.split("\n")
            # Add 4 more spaces to each line (8 total for method body)
            aio_body_indented = "\n".join("        " + line if line.strip() else "" for line in aio_body_lines)
            aio_wrapper_method = (
                f'    async def {aio_method_name}(cls: type["{class_name}"], {param_str}){async_return_str}:\n'
                f"{aio_body_indented}"
            )
            wrapper_functions_code = aio_wrapper_method
        else:
            # Sync-only classmethod: no async wrapper needed
            wrapper_functions_code = ""
            aio_body = None
    elif method_type == "staticmethod":
        if aio_body is not None:
            # Async staticmethod: generate async method (no self/cls)
            # aio_body is indented with 4 spaces, needs 8 spaces for method body
            aio_body_lines = aio_body.split("\n")
            # Add 4 more spaces to each line (8 total for method body)
            aio_body_indented = "\n".join("        " + line if line.strip() else "" for line in aio_body_lines)
            aio_wrapper_method = (
                f"    async def {aio_method_name}({param_str}){async_return_str}:\n" f"{aio_body_indented}"
            )
            wrapper_functions_code = aio_wrapper_method
        else:
            # Sync-only staticmethod: no async wrapper needed
            wrapper_functions_code = ""
            aio_body = None
    else:
        # Fallback - should not happen
        wrapper_functions_code = ""

    # Extract parameter names (excluding 'self'/'cls') for the call, with proper varargs handling
    param_call_parts = []
    for i, (name, param) in enumerate(sig.parameters.items()):
        if skip_first_param and i == 0:
            continue
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            param_call_parts.append(f"*{name}")
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            param_call_parts.append(f"**{name}")
        elif param.kind == inspect.Parameter.KEYWORD_ONLY:
            param_call_parts.append(f"{name}={name}")
        else:
            param_call_parts.append(name)

    # Build parameterized wrapper class/function name for decorator
    decorator_typevars = []

    # Add typing.Self for OWNER_TYPE if method uses Self
    if uses_self_type:
        decorator_typevars.append("typing.Self")

    # Add parent class's type variables
    if generic_typevars:
        decorator_typevars.extend(list(generic_typevars.keys()))

    # Choose the appropriate decorator function based on method type
    if method_type == "classmethod":
        decorator_func = "wrapped_classmethod"
    elif method_type == "staticmethod":
        decorator_func = "wrapped_staticmethod"
    else:
        decorator_func = "wrapped_method"

    # Build the method body - contains sync wrapper logic
    # For async methods, we'll pass the async wrapper to the decorator
    # For sync-only methods, use plain Python decorators (no descriptor magic needed)

    if aio_body is not None:
        # Async method: use descriptor decorator with async wrapper method
        # Reference the method directly (we're inside the class, so no need for class qualifier)
        decorator_line = f"@{decorator_func}({aio_method_name})"
        # Method body contains sync wrapper logic
        # For instance methods, need to adjust sync_method_body to work as method body
        # sync_method_body is indented with 4 spaces, method body needs 8 spaces
        if method_type == "instance":
            # Remove wrapper_instance parameter from sync_method_body since it will be 'self'
            method_body_lines = sync_method_body.replace("wrapper_instance", "self").split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()
        elif method_type == "classmethod":
            # Remove wrapper_class parameter from sync_method_body since it will be 'cls'
            method_body_lines = sync_method_body.replace("wrapper_class", "cls").split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()
        else:  # staticmethod
            # No replacement needed for staticmethods, but need to add indentation
            method_body_lines = sync_method_body.split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()
    else:
        # Sync-only method: use plain Python decorators, no descriptor needed
        # Method body contains sync wrapper logic directly
        if method_type == "instance":
            # Plain instance method - no decorator needed
            decorator_line = ""
            method_body_lines = sync_method_body.replace("wrapper_instance", "self").split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()
        elif method_type == "classmethod":
            # Use plain @classmethod decorator
            decorator_line = "@classmethod"
            method_body_lines = sync_method_body.replace("wrapper_class", "cls").split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()
        else:  # staticmethod
            # Use plain @staticmethod decorator
            decorator_line = "@staticmethod"
            method_body_lines = sync_method_body.split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()

    # Build the function definition line
    if method_type in ("classmethod", "staticmethod"):
        # Use dummy_param_str which includes cls for classmethods (for type checking only)
        def_line = f"    def {method_name}({dummy_param_str}){sync_return_str}:"
    else:
        # For instance methods, add self parameter to signature for dummy method
        # (param_str already excludes self since it was skipped, but body uses self)
        if param_str:
            instance_param_str = f"self, {param_str}"
        else:
            instance_param_str = "self"
        def_line = f"    def {method_name}({instance_param_str}){sync_return_str}:"

    # Build the method code - handle decorator line differently for sync-only vs async
    if decorator_line:
        # Has decorator (either descriptor or plain Python decorator)
        sync_method_code = f"    {decorator_line}\n{def_line}\n        {method_body}"
    else:
        # No decorator (plain instance method)
        sync_method_code = f"{def_line}\n        {method_body}"

    return wrapper_functions_code, sync_method_code


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
    # First collect classmethod and staticmethod (they won't show up in getmembers as functions)
    classmethod_staticmethod_names = set()
    for name, attr in cls.__dict__.items():
        if name.startswith("_"):
            continue
        if isinstance(attr, classmethod):
            methods.append((name, attr.__func__, "classmethod"))
            classmethod_staticmethod_names.add(name)
        elif isinstance(attr, staticmethod):
            methods.append((name, attr.__func__, "staticmethod"))
            classmethod_staticmethod_names.add(name)

    # Then collect regular instance methods (excluding those already collected as classmethod/staticmethod)
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if not name.startswith("_") and name in cls.__dict__ and name not in classmethod_staticmethod_names:
            methods.append((name, method, "instance"))

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

    # Register this class in synchronized_types so Self references work
    # This allows methods returning Self to be properly wrapped
    synchronized_types_with_self = synchronized_types.copy()
    synchronized_types_with_self[cls] = (current_target_module, cls.__name__)

    # Generate method wrapper classes and method code
    # Note: async wrapper methods are now generated inside the class, not as module-level functions
    method_async_wrappers = []  # Collect async wrapper methods to add to class
    method_definitions = []

    # Collect helpers from all methods
    all_helpers_dict = {}

    for method_name, method, method_type in methods:
        # Get helpers for this method's return type
        annotations = inspect.get_annotations(method, eval_str=True, globals=globals_dict)
        sig = inspect.signature(method)
        return_annotation = annotations.get("return", sig.return_annotation)
        # Check if typing.Self is used
        uses_self_type = _contains_self_type(return_annotation) or any(
            _contains_self_type(ann) for ann in annotations.values()
        )
        # Get impl class for Self resolution
        impl_class = None
        for cls_key, (mod, name) in synchronized_types_with_self.items():
            if mod == current_target_module and name == cls.__name__:
                impl_class = cls_key
                break
        transformer_annotation = return_annotation
        if uses_self_type and impl_class is not None:
            if return_annotation is typing.Self:
                transformer_annotation = impl_class
        return_transformer = create_transformer(transformer_annotation, synchronized_types)
        method_helpers = return_transformer.get_wrapper_helpers(
            synchronized_types_with_self, current_target_module, synchronizer_name, indent="    "
        )
        # Merge into all_helpers_dict (deduplicates by key)
        all_helpers_dict.update(method_helpers)

        wrapper_functions_code, sync_method_code = compile_method_wrapper(
            method,
            method_name,
            synchronizer_name,
            synchronized_types_with_self,  # Use the version with self registered
            origin_module,
            cls.__name__,
            current_target_module,
            method_type=method_type,
            globals_dict=globals_dict,
            generic_typevars=generic_typevars if generic_typevars else None,
        )
        if wrapper_functions_code:
            # Async wrapper methods go inside the class, not as module-level functions
            method_async_wrappers.append(wrapper_functions_code)
        method_definitions.append(sync_method_code)

    # Generate helpers section for the class
    helpers_code = "\n".join(all_helpers_dict.values()) if all_helpers_dict else ""
    helpers_section = f"\n{helpers_code}\n" if helpers_code else ""

    # Generate async wrapper methods section (methods inside the class)
    async_wrappers_section = "\n".join(method_async_wrappers) if method_async_wrappers else ""
    if async_wrappers_section:
        async_wrappers_section = f"\n{async_wrappers_section}"

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
{class_attrs}{helpers_section}{async_wrappers_section}

{init_method}

{from_impl_method}

{properties_section}

{methods_section}"""

    # Combine all the code
    # Note: async wrapper methods are now inside the class, so no module-level wrapper functions
    all_code = []
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

from synchronicity.descriptor import replace_with, wrapped_classmethod, wrapped_method, wrapped_staticmethod
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
    uses_self_type = False

    # Extract from standalone functions
    for func in functions:
        annotations = inspect.get_annotations(func, eval_str=True)
        func_typevars = _extract_typevars_from_function(func, annotations)
        module_typevars.update(func_typevars)

    # Extract from class methods
    for cls in classes:
        # Check if any methods use typing.Self
        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not name.startswith("_") and name in cls.__dict__:
                annotations = inspect.get_annotations(method, eval_str=True)
                sig = inspect.signature(method)
                return_annotation = annotations.get("return", sig.return_annotation)
                has_self_in_return = _contains_self_type(return_annotation)
                has_self_in_params = any(_contains_self_type(ann) for ann in annotations.values())
                if has_self_in_return or has_self_in_params:
                    uses_self_type = True

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

    # Add OWNER_TYPE if any methods use typing.Self
    if uses_self_type:
        compiled_code.append("# OWNER_TYPE for methods using typing.Self")
        compiled_code.append('OWNER_TYPE = typing.TypeVar("OWNER_TYPE")')
        compiled_code.append("")  # Add blank line

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
