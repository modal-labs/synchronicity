"""Main compilation module - imports from codegen package and provides compile_* functions."""

from __future__ import annotations

import inspect
import types
from typing import TYPE_CHECKING

from .codegen import (
    build_unwrap_expr,
    build_wrap_expr,
    format_return_types,
    format_type_annotation,
    get_wrapped_classes,
    is_async_generator,
    needs_translation,
    parse_parameters,
    translate_type_annotation,
)

if TYPE_CHECKING:
    from .synchronizer import Synchronizer


def _generate_weakref_import(wrapped_classes: dict[str, str]) -> str:
    """
    Generate weakref import if there are any wrapped classes.

    Args:
        wrapped_classes: Mapping of wrapper names to impl qualified names

    Returns:
        String containing weakref import, or empty string if no wrapped classes
    """
    if not wrapped_classes:
        return ""

    return "import weakref"


def _qualify_type_for_annotation(
    wrapper_type: str,
    wrapped_classes: dict[str, str],
    local_wrapped_classes: dict[str, str],
    cross_module_imports: dict[str, set[str]],
) -> str:
    """
    Qualify a wrapper type name for use in a type annotation.

    For cross-module types, returns the fully qualified name (e.g., "multifile.a.A").
    For local types, returns just the class name (e.g., "A").

    Args:
        wrapper_type: The wrapper type string (e.g., "A" or "list[A]")
        wrapped_classes: Dict mapping wrapper names to impl qualified names
        local_wrapped_classes: Dict of wrapped classes defined in the current module
        cross_module_imports: Dict mapping target modules to sets of imported class names

    Returns:
        The qualified type string
    """
    # Check if this is a simple wrapped class name
    if wrapper_type in wrapped_classes:
        # Check if it's cross-module
        if wrapper_type not in local_wrapped_classes:
            # Find which module it belongs to
            for target_module, class_names in cross_module_imports.items():
                if wrapper_type in class_names:
                    return f"{target_module}.{wrapper_type}"
        # Local class - return as-is
        return wrapper_type

    # For complex types (like list[A]), we'd need more sophisticated parsing
    # For now, return as-is
    return wrapper_type


def compile_function(
    f: types.FunctionType,
    target_module: str,
    synchronizer: Synchronizer,
    *,
    _all_wrapped_classes: dict[str, str] | None = None,
    _local_wrapped_classes: dict[str, str] | None = None,
    _cross_module_imports: dict[str, set[str]] | None = None,
) -> str:
    """
    Compile a function into a wrapper class that provides both sync and async versions.
    Uses the decorator pattern similar to method wrapping.

    Args:
        f: The function to compile
        target_module: The module name where the original function is located
        synchronizer: The Synchronizer instance

    Internal args (computed by compile_module):
        _all_wrapped_classes: Global wrapped classes mapping (for type translation)
        _local_wrapped_classes: Wrapped classes local to the current module
        _cross_module_imports: Cross-module import information

    Returns:
        String containing the generated wrapper class and decorated function code
    """
    synchronizer_name = synchronizer._name

    # Derive wrapped_classes and related data from the synchronizer if not provided
    if _all_wrapped_classes is None:
        wrapped_classes = get_wrapped_classes(synchronizer._wrapped)
        local_wrapped_classes = wrapped_classes
        cross_module_imports = {}
    else:
        wrapped_classes = _all_wrapped_classes
        local_wrapped_classes = _local_wrapped_classes or {}
        cross_module_imports = _cross_module_imports or {}

    # Get function signature and annotations
    sig = inspect.signature(f)
    return_annotation = sig.return_annotation

    # Parse parameters - we'll need to translate types
    params = []
    call_args = []
    unwrap_stmts = []

    for name, param in sig.parameters.items():
        # Translate the parameter type annotation
        if param.annotation != param.empty:
            wrapper_type, impl_type = translate_type_annotation(param.annotation, wrapped_classes, target_module)
            param_str = f"{name}: {wrapper_type}"

            # Generate unwrap code if needed
            if needs_translation(param.annotation, wrapped_classes):
                unwrap_expr = build_unwrap_expr(param.annotation, wrapped_classes, name)
                unwrap_stmts.append(f"    {name}_impl = {unwrap_expr}")
                call_args.append(f"{name}_impl")
            else:
                call_args.append(name)
        else:
            param_str = name
            call_args.append(name)

        if param.default is not param.empty:
            default_val = repr(param.default)
            param_str += f" = {default_val}"

        params.append(param_str)

    param_str = ", ".join(params)
    call_args_str = ", ".join(call_args)
    unwrap_code = "\n".join(unwrap_stmts) if unwrap_stmts else ""

    # Check if it's an async generator
    is_async_gen = is_async_generator(f, return_annotation)

    # Check if it's an async function (coroutine or async generator)
    is_async_func = inspect.iscoroutinefunction(f) or is_async_gen

    # For non-async functions, generate simple wrapper without @wrapped_function decorator or .aio()
    if not is_async_func:
        # Build simple wrapper function
        if needs_translation(return_annotation, wrapped_classes):
            wrapper_return_type, _ = translate_type_annotation(return_annotation, wrapped_classes, target_module)
            wrap_expr = build_wrap_expr(
                return_annotation, wrapped_classes, "result", local_wrapped_classes, cross_module_imports
            )
            function_body = f"""    result = impl_function({call_args_str})
    return {wrap_expr}"""
            return_str = f" -> {wrapper_return_type}"
        else:
            # Format return type if available
            if return_annotation != inspect.Signature.empty:
                return_str = f" -> {format_type_annotation(return_annotation)}"
            else:
                return_str = ""
            function_body = f"""    return impl_function({call_args_str})"""

        # Add impl_function reference and unwrap statements
        impl_ref = f"    impl_function = {target_module}.{f.__name__}"
        if unwrap_code:
            function_body = f"{impl_ref}\n{unwrap_code}\n{function_body}"
        else:
            function_body = f"{impl_ref}\n{function_body}"

        # Generate simple function (no decorator, no wrapper class)
        return f"""def {f.__name__}({param_str}){return_str}:
{function_body}"""

    # Format return types - translate them
    if needs_translation(return_annotation, wrapped_classes):
        wrapper_return_type, impl_return_type = translate_type_annotation(
            return_annotation, wrapped_classes, target_module
        )
        if is_async_gen:
            # Extract yield type from AsyncGenerator
            if hasattr(return_annotation, "__args__") and return_annotation.__args__:
                yield_type = return_annotation.__args__[0]
                wrapper_yield_type, impl_yield_type = translate_type_annotation(
                    yield_type, wrapped_classes, target_module
                )
                # Quote wrapped class names in generic types for forward references
                # Use fully qualified names for cross-module types
                if wrapper_yield_type in wrapped_classes and wrapper_yield_type not in local_wrapped_classes:
                    # Cross-module type - use fully qualified name
                    qualified_yield_type = _qualify_type_for_annotation(
                        wrapper_yield_type, wrapped_classes, local_wrapped_classes, cross_module_imports
                    )
                    quoted_yield_type = f'"{qualified_yield_type}"'
                elif wrapper_yield_type in wrapped_classes:
                    # Local wrapped type - just quote it
                    quoted_yield_type = f'"{wrapper_yield_type}"'
                else:
                    # Not a wrapped type - don't quote
                    quoted_yield_type = wrapper_yield_type

                sync_return_str = f" -> typing.Generator[{quoted_yield_type}, None, None]"
                if len(return_annotation.__args__) > 1:
                    send_type = return_annotation.__args__[1]
                    send_type_str = format_type_annotation(send_type)
                    async_return_str = f" -> typing.AsyncGenerator[{quoted_yield_type}, {send_type_str}]"
                else:
                    async_return_str = f" -> typing.AsyncGenerator[{quoted_yield_type}]"
            else:
                sync_return_str = " -> typing.Generator"
                async_return_str = " -> typing.AsyncGenerator"
            # For generators, descriptor and final function have the same return type
            sync_return_str_descriptor = sync_return_str
            async_return_str_descriptor = async_return_str
        else:
            # For descriptor class methods, always quote wrapped class names to handle forward references
            # For final function, only quote if it's a cross-module type (in TYPE_CHECKING)

            # Check if the return type contains any wrapped classes from other modules
            has_cross_module_class = False
            if needs_translation(return_annotation, wrapped_classes):
                # Return type contains wrapped classes - check if they're cross-module
                # Get all wrapped class names that appear in the return type
                for class_name in wrapped_classes.keys():
                    if class_name in wrapper_return_type and class_name not in local_wrapped_classes:
                        # Found a cross-module class reference
                        has_cross_module_class = True
                        break

            if has_cross_module_class:
                # Has cross-module class - use fully qualified name and quote
                qualified_type = _qualify_type_for_annotation(
                    wrapper_return_type, wrapped_classes, local_wrapped_classes, cross_module_imports
                )
                sync_return_str_descriptor = f' -> "{qualified_type}"'
                async_return_str_descriptor = f' -> "{qualified_type}"'
                sync_return_str = f' -> "{qualified_type}"'
                async_return_str = f' -> "{qualified_type}"'
            elif wrapper_return_type in local_wrapped_classes:
                # Simple local class - quote only for descriptor (forward reference)
                sync_return_str_descriptor = f' -> "{wrapper_return_type}"'
                async_return_str_descriptor = f' -> "{wrapper_return_type}"'
                sync_return_str = f" -> {wrapper_return_type}"
                async_return_str = f" -> {wrapper_return_type}"
            else:
                # No wrapped classes or complex generic - don't quote
                sync_return_str_descriptor = f" -> {wrapper_return_type}"
                async_return_str_descriptor = f" -> {wrapper_return_type}"
                sync_return_str = f" -> {wrapper_return_type}"
                async_return_str = f" -> {wrapper_return_type}"
    else:
        sync_return_str, async_return_str = format_return_types(return_annotation, is_async_gen)
        sync_return_str_descriptor = sync_return_str
        async_return_str_descriptor = async_return_str

    # Generate the wrapper class
    wrapper_class_name = f"_{f.__name__}"

    # Determine if we need to wrap the return value
    needs_return_wrap = needs_translation(return_annotation, wrapped_classes)

    # Build the aio() method body
    if is_async_gen:
        # For generators, wrap each yielded item
        if needs_return_wrap and hasattr(return_annotation, "__args__"):
            yield_type = return_annotation.__args__[0]
            wrap_expr = build_wrap_expr(
                yield_type, wrapped_classes, "item", local_wrapped_classes, cross_module_imports
            )
            aio_body = f"""        gen = impl_function({call_args_str})
        async for item in self._synchronizer._run_generator_async(gen):
            yield {wrap_expr}"""
        else:
            aio_body = f"""        gen = impl_function({call_args_str})
        async for item in self._synchronizer._run_generator_async(gen):
            yield item"""
    elif is_async_func:
        # For regular async functions
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(
                return_annotation, wrapped_classes, "result", local_wrapped_classes, cross_module_imports
            )
            aio_body = f"""        result = await impl_function({call_args_str})
        return {wrap_expr}"""
        else:
            aio_body = f"""        return await impl_function({call_args_str})"""
    else:
        # For non-async functions, call directly (no await, no synchronizer)
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(
                return_annotation, wrapped_classes, "result", local_wrapped_classes, cross_module_imports
            )
            aio_body = f"""        result = impl_function({call_args_str})
        return {wrap_expr}"""
        else:
            aio_body = f"""        return impl_function({call_args_str})"""

    # Build unwrap section for aio() if needed
    aio_impl_ref = f"        impl_function = {target_module}.{f.__name__}"
    aio_unwrap = f"\n{aio_impl_ref}"
    if unwrap_code:
        # Adjust indentation for aio method (8 spaces)
        aio_unwrap_lines = [line.replace("    ", "        ", 1) for line in unwrap_stmts]
        aio_unwrap += "\n" + "\n".join(aio_unwrap_lines)

    # Build unwrap section for __call__ if needed - uses original call_args_str
    # which has the wrapper parameter names, not the impl ones

    if unwrap_code:
        # For __call__, we need to unwrap but then pass to sync_wrapper_function
        # The sync_wrapper_function will handle the actual impl call
        pass  # __call__ passes through to sync_wrapper_function which handles unwrapping

    wrapper_class_code = f"""class {wrapper_class_name}:
    _synchronizer = get_synchronizer('{synchronizer_name}')
    _impl_function = {target_module}.{f.__name__}
    _sync_wrapper_function: typing.Callable[..., typing.Any]

    def __init__(self, sync_wrapper_function: typing.Callable[..., typing.Any]):
        self._sync_wrapper_function = sync_wrapper_function

    def __call__(self, {param_str}){sync_return_str_descriptor}:
        return self._sync_wrapper_function({", ".join([p.split(":")[0].split("=")[0].strip() for p in params])})

    async def aio(self, {param_str}){async_return_str_descriptor}:{aio_unwrap}
{aio_body}
"""

    # Build the sync wrapper function code
    if is_async_gen:
        # For generators, wrap each yielded item
        if needs_return_wrap and hasattr(return_annotation, "__args__"):
            yield_type = return_annotation.__args__[0]
            wrap_expr = build_wrap_expr(
                yield_type, wrapped_classes, "item", local_wrapped_classes, cross_module_imports
            )
            sync_gen_body = f"""    gen = impl_function({call_args_str})
    for item in get_synchronizer('{synchronizer_name}')._run_generator_sync(gen):
        yield {wrap_expr}"""
        else:
            sync_gen_body = f"""    gen = impl_function({call_args_str})
    yield from get_synchronizer('{synchronizer_name}')._run_generator_sync(gen)"""
        sync_function_body = sync_gen_body
    elif is_async_func:
        # For regular async functions, use synchronizer
        sync_runner = f"get_synchronizer('{synchronizer_name}')._run_function_sync"
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(
                return_annotation, wrapped_classes, "result", local_wrapped_classes, cross_module_imports
            )
            sync_function_body = f"""    result = {sync_runner}(impl_function({call_args_str}))
    return {wrap_expr}"""
        else:
            sync_function_body = f"""    return {sync_runner}(impl_function({call_args_str}))"""
    else:
        # For non-async functions, call directly without synchronizer
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(
                return_annotation, wrapped_classes, "result", local_wrapped_classes, cross_module_imports
            )
            sync_function_body = f"""    result = impl_function({call_args_str})
    return {wrap_expr}"""
        else:
            sync_function_body = f"""    return impl_function({call_args_str})"""

    # Add impl_function reference and unwrap statements to sync function if needed
    impl_ref = f"    impl_function = {target_module}.{f.__name__}"
    if unwrap_code:
        sync_function_body = f"{impl_ref}\n{unwrap_code}\n{sync_function_body}"
    else:
        sync_function_body = f"{impl_ref}\n{sync_function_body}"

    sync_function_code = f"""@wrapped_function({wrapper_class_name})
def {f.__name__}({param_str}){sync_return_str}:
{sync_function_body}"""

    return f"{wrapper_class_code}\n{sync_function_code}"


def compile_method_wrapper(
    method: types.FunctionType,
    method_name: str,
    synchronizer: Synchronizer,
    target_module: str,
    class_name: str,
    *,
    _all_wrapped_classes: dict[str, str] | None = None,
    _local_wrapped_classes: dict[str, str] | None = None,
    _cross_module_imports: dict[str, set[str]] | None = None,
) -> tuple[str, str]:
    """
    Compile a method wrapper class that provides both sync and async versions.

    This generates a ClassName_methodname style class that works with the @wrapped_method decorator.

    Args:
        method: The method to wrap
        method_name: The name of the method
        synchronizer: The Synchronizer instance
        target_module: The module where the original class is located
        class_name: The name of the class containing the method

    Internal args (computed by compile_class/compile_module):
        _all_wrapped_classes: Global wrapped classes mapping (for type translation)
        _local_wrapped_classes: Wrapped classes local to the current module
        _cross_module_imports: Cross-module import information

    Returns:
        Tuple of (wrapper_class_code, sync_method_code)
    """
    synchronizer_name = synchronizer._name

    # Derive wrapped_classes and related data from the synchronizer if not provided
    if _all_wrapped_classes is None:
        wrapped_classes = get_wrapped_classes(synchronizer._wrapped)
        local_wrapped_classes = wrapped_classes
        cross_module_imports = {}
    else:
        wrapped_classes = _all_wrapped_classes
        local_wrapped_classes = _local_wrapped_classes or {}
        cross_module_imports = _cross_module_imports or {}

    # Get method signature and annotations
    sig = inspect.signature(method)
    return_annotation = sig.return_annotation

    # Parse parameters - we'll need to translate types
    params = []
    params_descriptor = []  # For wrapper class __call__, with quoted wrapped types
    call_args = []
    unwrap_stmts = []

    for name, param in sig.parameters.items():
        if name == "self":
            continue

        # Translate the parameter type annotation
        if param.annotation != param.empty:
            wrapper_type, impl_type = translate_type_annotation(param.annotation, wrapped_classes, target_module)
            param_str = f"{name}: {wrapper_type}"

            # For descriptor __call__, quote wrapped class names for forward references
            if wrapper_type in wrapped_classes:
                param_str_descriptor = f'{name}: "{wrapper_type}"'
            else:
                param_str_descriptor = param_str

            # Generate unwrap code if needed
            if needs_translation(param.annotation, wrapped_classes):
                unwrap_expr = build_unwrap_expr(param.annotation, wrapped_classes, name)
                unwrap_stmts.append(f"        {name}_impl = {unwrap_expr}")
                call_args.append(f"{name}_impl")
            else:
                call_args.append(name)
        else:
            param_str = name
            param_str_descriptor = name
            call_args.append(name)

        if param.default is not param.empty:
            default_val = repr(param.default)
            param_str += f" = {default_val}"
            param_str_descriptor += f" = {default_val}"

        params.append(param_str)
        params_descriptor.append(param_str_descriptor)

    param_str = ", ".join(params)
    param_str_descriptor = ", ".join(params_descriptor)
    call_args_str = ", ".join(call_args)
    unwrap_code = "\n".join(unwrap_stmts) if unwrap_stmts else ""

    # Check if it's an async generator
    is_async_gen = is_async_generator(method, return_annotation)

    # Check if it's an async method (coroutine or async generator)
    is_async_method = inspect.iscoroutinefunction(method) or is_async_gen

    # For non-async methods, generate simple proxy method without wrapper class
    if not is_async_method:
        # Build impl call arguments (with unwrapped values)
        impl_call_args = f"self._impl_instance{', ' + call_args_str if call_args_str else ''}"

        # Build method body
        impl_ref = f"        impl_function = {target_module}.{class_name}.{method_name}"

        if needs_translation(return_annotation, wrapped_classes):
            wrapper_return_type, _ = translate_type_annotation(return_annotation, wrapped_classes, target_module)
            wrap_expr = build_wrap_expr(
                return_annotation, wrapped_classes, "result", local_wrapped_classes, cross_module_imports
            )
            method_body = f"""        result = impl_function({impl_call_args})
        return {wrap_expr}"""
            return_str = f" -> {wrapper_return_type}"
        else:
            # Format return type if available
            if return_annotation != inspect.Signature.empty:
                return_str = f" -> {format_type_annotation(return_annotation)}"
            else:
                return_str = ""
            method_body = f"""        return impl_function({impl_call_args})"""

        # Add unwrap statements if needed
        if unwrap_code:
            method_body = f"{impl_ref}\n{unwrap_code}\n{method_body}"
        else:
            method_body = f"{impl_ref}\n{method_body}"

        # Generate simple method (no wrapper class, no decorator)
        simple_method = f"""    def {method_name}(self, {param_str}){return_str}:
{method_body}"""

        # Return empty wrapper class code and the simple method
        return "", simple_method

    # Format return types - translate them
    if needs_translation(return_annotation, wrapped_classes):
        wrapper_return_type, impl_return_type = translate_type_annotation(
            return_annotation, wrapped_classes, target_module
        )
        if is_async_gen:
            # Extract yield type from AsyncGenerator
            if hasattr(return_annotation, "__args__") and return_annotation.__args__:
                yield_type = return_annotation.__args__[0]
                wrapper_yield_type, impl_yield_type = translate_type_annotation(
                    yield_type, wrapped_classes, target_module
                )
                # Quote wrapped class names in generic types for forward references
                # Use fully qualified names for cross-module types
                if wrapper_yield_type in wrapped_classes and wrapper_yield_type not in local_wrapped_classes:
                    # Cross-module type - use fully qualified name
                    qualified_yield_type = _qualify_type_for_annotation(
                        wrapper_yield_type, wrapped_classes, local_wrapped_classes, cross_module_imports
                    )
                    quoted_yield_type = f'"{qualified_yield_type}"'
                elif wrapper_yield_type in wrapped_classes:
                    # Local wrapped type - just quote it
                    quoted_yield_type = f'"{wrapper_yield_type}"'
                else:
                    # Not a wrapped type - don't quote
                    quoted_yield_type = wrapper_yield_type

                sync_return_str = f" -> typing.Generator[{quoted_yield_type}, None, None]"
                if len(return_annotation.__args__) > 1:
                    send_type = return_annotation.__args__[1]
                    send_type_str = format_type_annotation(send_type)
                    async_return_str = f" -> typing.AsyncGenerator[{quoted_yield_type}, {send_type_str}]"
                else:
                    async_return_str = f" -> typing.AsyncGenerator[{quoted_yield_type}]"
            else:
                sync_return_str = " -> typing.Generator"
                async_return_str = " -> typing.AsyncGenerator"
            # For generators, descriptor and final function have the same return type
            sync_return_str_descriptor = sync_return_str
            async_return_str_descriptor = async_return_str
        else:
            # For descriptor class methods, quote wrapped class names to handle forward references
            # Handle both simple types (Node) and complex types (list[Node])
            quoted_wrapper_type = wrapper_return_type
            for wrapper_name in wrapped_classes.keys():
                # Quote wrapped class names wherever they appear
                # Handle standalone class names
                if wrapper_name == wrapper_return_type:
                    quoted_wrapper_type = f'"{wrapper_name}"'
                    break
                # Handle class names within generic types (e.g., list[Node] -> list["Node"])
                elif wrapper_name in wrapper_return_type:
                    quoted_wrapper_type = wrapper_return_type.replace(wrapper_name, f'"{wrapper_name}"')
            # Both descriptor and final methods use quoted types for forward references
            sync_return_str_descriptor = f" -> {quoted_wrapper_type}"
            async_return_str_descriptor = f" -> {quoted_wrapper_type}"
            sync_return_str = f" -> {quoted_wrapper_type}"
            async_return_str = f" -> {quoted_wrapper_type}"
    else:
        sync_return_str, async_return_str = format_return_types(return_annotation, is_async_gen)
        sync_return_str_descriptor = sync_return_str
        async_return_str_descriptor = async_return_str

    # Generate the method wrapper class code
    wrapper_class_name = f"{class_name}_{method_name}"

    # Determine if we need to wrap the return value
    needs_return_wrap = needs_translation(return_annotation, wrapped_classes)

    # Build the impl call arguments (with unwrapped values)
    impl_call_args = f"self._impl_instance{', ' + call_args_str if call_args_str else ''}"

    # Build the aio() method body
    if is_async_gen:
        # For generators, wrap each yielded item
        if needs_return_wrap and hasattr(return_annotation, "__args__"):
            yield_type = return_annotation.__args__[0]
            wrap_expr = build_wrap_expr(
                yield_type, wrapped_classes, "item", local_wrapped_classes, cross_module_imports
            )
            aio_body = f"""        gen = impl_function({impl_call_args})
        async for item in self._synchronizer._run_generator_async(gen):
            yield {wrap_expr}"""
        else:
            aio_body = f"""        gen = impl_function({impl_call_args})
        async for item in self._synchronizer._run_generator_async(gen):
            yield item"""
    elif is_async_method:
        # For regular async methods
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(
                return_annotation, wrapped_classes, "result", local_wrapped_classes, cross_module_imports
            )
            aio_body = f"""        result = await impl_function({impl_call_args})
        return {wrap_expr}"""
        else:
            aio_body = f"""        return await impl_function({impl_call_args})"""
    else:
        # For non-async methods, call directly (no await, no synchronizer)
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(
                return_annotation, wrapped_classes, "result", local_wrapped_classes, cross_module_imports
            )
            aio_body = f"""        result = impl_function({impl_call_args})
        return {wrap_expr}"""
        else:
            aio_body = f"""        return impl_function({impl_call_args})"""

    # Build unwrap section for aio() if needed
    aio_impl_ref = f"        impl_function = {target_module}.{class_name}.{method_name}"
    aio_unwrap = f"\n{aio_impl_ref}"
    if unwrap_code:
        # Adjust indentation for aio method (8 spaces)
        aio_unwrap_lines = [line.replace("        ", "        ", 1) for line in unwrap_stmts]
        aio_unwrap += "\n" + "\n".join(aio_unwrap_lines)

    # For __call__, we need to pass the original parameter names (not _impl versions)
    # because __call__ passes through to the sync wrapper method which handles unwrapping
    call_params = ", ".join([p.split(":")[0].split("=")[0].strip() for p in params])

    # Build the wrapper class
    wrapper_class_code = f"""class {wrapper_class_name}:
    _synchronizer = get_synchronizer('{synchronizer_name}')
    _impl_instance: {target_module}.{class_name}
    _sync_wrapper_method: typing.Callable[..., typing.Any]

    def __init__(self, wrapper_instance: "{class_name}", unbound_sync_wrapper_method: typing.Callable[..., typing.Any]):
        self._wrapper_instance = wrapper_instance
        self._impl_instance = wrapper_instance._impl_instance
        self._unbound_sync_wrapper_method = unbound_sync_wrapper_method

    def __call__(self, {param_str_descriptor}){sync_return_str_descriptor}:
        return self._unbound_sync_wrapper_method(self._wrapper_instance, {call_params})

    async def aio(self, {param_str_descriptor}){async_return_str_descriptor}:{aio_unwrap}
{aio_body}
"""

    # Build the sync wrapper method code
    if is_async_gen:
        # For generators, wrap each yielded item
        if needs_return_wrap and hasattr(return_annotation, "__args__"):
            yield_type = return_annotation.__args__[0]
            wrap_expr = build_wrap_expr(
                yield_type, wrapped_classes, "item", local_wrapped_classes, cross_module_imports
            )
            sync_method_body = f"""        gen = impl_function({impl_call_args})
        for item in self._synchronizer._run_generator_sync(gen):
            yield {wrap_expr}"""
        else:
            sync_method_body = f"""        gen = impl_function({impl_call_args})
        yield from self._synchronizer._run_generator_sync(gen)"""
    elif is_async_method:
        # For regular async methods, use synchronizer
        sync_runner = "self._synchronizer._run_function_sync"
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(
                return_annotation, wrapped_classes, "result", local_wrapped_classes, cross_module_imports
            )
            sync_method_body = f"""        result = {sync_runner}(impl_function({impl_call_args}))
        return {wrap_expr}"""
        else:
            sync_method_body = f"""        return {sync_runner}(impl_function({impl_call_args}))"""
    else:
        # For non-async methods, call directly without synchronizer
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(
                return_annotation, wrapped_classes, "result", local_wrapped_classes, cross_module_imports
            )
            sync_method_body = f"""        result = impl_function({impl_call_args})
        return {wrap_expr}"""
        else:
            sync_method_body = f"""        return impl_function({impl_call_args})"""

    # Add impl_function reference and unwrap statements to sync method if needed
    impl_ref = f"        impl_function = {target_module}.{class_name}.{method_name}"
    if unwrap_code:
        sync_method_body = f"{impl_ref}\n{unwrap_code}\n{sync_method_body}"
    else:
        sync_method_body = f"{impl_ref}\n{sync_method_body}"

    sync_method_code = f"""    @wrapped_method({wrapper_class_name})
    def {method_name}(self, {param_str}){sync_return_str}:
{sync_method_body}"""

    return wrapper_class_code, sync_method_code


def compile_class(
    cls: type,
    target_module: str,
    synchronizer: Synchronizer,
    *,
    _all_wrapped_classes: dict[str, str] | None = None,
    _local_wrapped_classes: dict[str, str] | None = None,
    _cross_module_imports: dict[str, set[str]] | None = None,
) -> str:
    """
    Compile a class into a wrapper class where all methods are wrapped with sync/async versions.

    Args:
        cls: The class to compile
        target_module: The module name where the original class is located
        synchronizer: The Synchronizer instance

    Internal args (computed by compile_module):
        _all_wrapped_classes: Global wrapped classes mapping (for type translation)
        _local_wrapped_classes: Wrapped classes local to the current module
        _cross_module_imports: Cross-module import information

    Returns:
        String containing the generated wrapper class code
    """
    synchronizer_name = synchronizer._name

    # Derive wrapped_classes and related data from the synchronizer if not provided
    if _all_wrapped_classes is None:
        wrapped_classes = get_wrapped_classes(synchronizer._wrapped)
        local_wrapped_classes = wrapped_classes
        cross_module_imports = {}
    else:
        wrapped_classes = _all_wrapped_classes
        local_wrapped_classes = _local_wrapped_classes or {}
        cross_module_imports = _cross_module_imports or {}

    # Get all methods from the class (both async and non-async)
    methods = []
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if not name.startswith("_"):
            # Wrap all public methods (async and non-async)
            methods.append((name, method))

    # Get class attributes from annotations
    attributes = []
    if hasattr(cls, "__annotations__"):
        for name, annotation in cls.__annotations__.items():
            if not name.startswith("_"):
                attr_type = format_type_annotation(annotation)
                attributes.append((name, attr_type))

    # Generate method wrapper classes and method code
    method_wrapper_classes = []
    method_definitions = []

    for method_name, method in methods:
        wrapper_class_code, sync_method_code = compile_method_wrapper(
            method,
            method_name,
            synchronizer,
            target_module,
            cls.__name__,
            _all_wrapped_classes=wrapped_classes,
            _local_wrapped_classes=local_wrapped_classes,
            _cross_module_imports=cross_module_imports,
        )
        # Only add wrapper class if it's not empty (non-async methods return empty string)
        if wrapper_class_code:
            method_wrapper_classes.append(wrapper_class_code)
        method_definitions.append(sync_method_code)

    # Get __init__ signature
    init_method = getattr(cls, "__init__", None)
    if init_method and init_method is not object.__init__:
        sig = inspect.signature(init_method)
        init_signature, _, init_call_args_list = parse_parameters(sig, skip_self=True)
        # For __init__, we want keyword arguments in the call
        init_call = ", ".join(f"{name}={name}" for name in init_call_args_list)
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

    # Generate _from_impl classmethod
    from_impl_method = f"""    @classmethod
    def _from_impl(cls, impl_instance: {target_module}.{cls.__name__}) -> "{cls.__name__}":
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

    wrapper_class_code = f"""class {cls.__name__}:
    \"\"\"Wrapper class for {target_module}.{cls.__name__} with sync/async method support\"\"\"

    _synchronizer = get_synchronizer('{synchronizer_name}')
    _instance_cache: weakref.WeakValueDictionary = weakref.WeakValueDictionary()

    def __init__(self, {init_signature}):
        self._impl_instance = {target_module}.{cls.__name__}({init_call})

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
    wrapped_items: dict,
    all_wrapped_classes: dict[str, str],
) -> dict[str, set[str]]:
    """
    Detect which wrapped classes from other modules are referenced in this module.

    Args:
        module_name: The current module being compiled
        module_items: Items in the current module
        wrapped_items: All wrapped items across all modules
        all_wrapped_classes: Global dict of all wrapped classes

    Returns:
        Dict mapping target module names to sets of wrapper class names
    """
    cross_module_refs = {}  # target_module -> set of class names

    # Build a reverse mapping: impl_qualified_name -> (target_module, wrapper_name)
    impl_to_wrapper = {}
    for obj, (target_module, target_name) in wrapped_items.items():
        if isinstance(obj, type):
            impl_qualified_name = f"{obj.__module__}.{obj.__name__}"
            impl_to_wrapper[impl_qualified_name] = (target_module, target_name)

    # Check each item in this module for references to wrapped classes from other modules
    for obj, (target_module, target_name) in module_items.items():
        # Get signature if it's a function or class with methods
        if isinstance(obj, types.FunctionType):
            try:
                # Use get_annotations to resolve string annotations
                annotations = inspect.get_annotations(obj, eval_str=True)
                for param_name, annotation in annotations.items():
                    _check_annotation_for_cross_refs(annotation, module_name, impl_to_wrapper, cross_module_refs)
            except (NameError, AttributeError, TypeError):
                # Fall back to signature if get_annotations fails
                sig = inspect.signature(obj)
                for param in sig.parameters.values():
                    if param.annotation != param.empty:
                        _check_annotation_for_cross_refs(
                            param.annotation, module_name, impl_to_wrapper, cross_module_refs
                        )
                if sig.return_annotation != sig.empty:
                    _check_annotation_for_cross_refs(
                        sig.return_annotation, module_name, impl_to_wrapper, cross_module_refs
                    )
        elif isinstance(obj, type):
            # Check methods of the class
            for method_name, method in inspect.getmembers(obj, predicate=inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                try:
                    # Try to use get_annotations to resolve string annotations
                    annotations = inspect.get_annotations(method, eval_str=True)
                    for annotation in annotations.values():
                        _check_annotation_for_cross_refs(annotation, module_name, impl_to_wrapper, cross_module_refs)
                except (NameError, AttributeError, TypeError, ValueError):
                    # Fall back to signature
                    try:
                        sig = inspect.signature(method)
                        for param in sig.parameters.values():
                            if param.annotation != param.empty:
                                _check_annotation_for_cross_refs(
                                    param.annotation, module_name, impl_to_wrapper, cross_module_refs
                                )
                        if sig.return_annotation != sig.empty:
                            _check_annotation_for_cross_refs(
                                sig.return_annotation, module_name, impl_to_wrapper, cross_module_refs
                            )
                    except (ValueError, TypeError):
                        # Some built-in methods don't have signatures
                        continue

    return cross_module_refs


def _check_annotation_for_cross_refs(
    annotation,
    current_module: str,
    impl_to_wrapper: dict,
    cross_module_refs: dict,
) -> None:
    """Check a type annotation for references to wrapped classes from other modules."""
    # Handle direct class references
    if isinstance(annotation, type):
        impl_qualified_name = f"{annotation.__module__}.{annotation.__name__}"
        if impl_qualified_name in impl_to_wrapper:
            target_module, wrapper_name = impl_to_wrapper[impl_qualified_name]
            if target_module != current_module:
                if target_module not in cross_module_refs:
                    cross_module_refs[target_module] = set()
                cross_module_refs[target_module].add(wrapper_name)

    # Handle generic types (e.g., List[WrapperClass], Optional[WrapperClass])
    if hasattr(annotation, "__args__"):
        for arg in annotation.__args__:
            _check_annotation_for_cross_refs(arg, current_module, impl_to_wrapper, cross_module_refs)


def compile_module(
    module_name: str,
    synchronizer: Synchronizer,
) -> str:
    """
    Compile wrapped items for a single target module.

    Args:
        module_name: The target module name to generate (e.g., "multifile.a")
        synchronizer: The Synchronizer instance

    Returns:
        String containing compiled wrapper code for this module
    """
    wrapped_items = synchronizer._wrapped

    # Get all wrapped classes from the synchronizer
    all_wrapped_classes = get_wrapped_classes(wrapped_items)
    # Filter items for this specific module
    module_items = {
        obj: (tgt_mod, tgt_name) for obj, (tgt_mod, tgt_name) in wrapped_items.items() if tgt_mod == module_name
    }

    if not module_items:
        return ""

    # Collect unique implementation modules needed for this module
    impl_modules = set()
    for o, (target_module, target_name) in module_items.items():
        impl_modules.add(o.__module__)

    # Extract wrapped classes for this module (subset of all_wrapped_classes)
    wrapped_classes = {
        name: qual_name
        for name, qual_name in all_wrapped_classes.items()
        if any(qual_name == f"{o.__module__}.{o.__name__}" for o, _ in module_items.items() if isinstance(o, type))
    }

    # Detect cross-module references
    cross_module_imports = _get_cross_module_imports(module_name, module_items, wrapped_items, all_wrapped_classes)

    # Generate header with imports for all implementation modules
    imports = "\n".join(f"import {mod}" for mod in sorted(impl_modules))

    # Generate cross-module imports
    # Import the wrapper modules directly so pyright can resolve fully qualified names
    # Import cross-module wrapper classes directly (no longer behind TYPE_CHECKING)
    cross_module_import_strs = []
    for target_module in sorted(cross_module_imports.keys()):
        cross_module_import_strs.append(f"import {target_module}")

    cross_module_imports_str = "\n".join(cross_module_import_strs) if cross_module_import_strs else ""

    header = f"""import typing

{imports}

from synchronicity2.descriptor import wrapped_function, wrapped_method
from synchronicity2.synchronizer import get_synchronizer
"""

    if cross_module_imports_str:
        header += f"\n{cross_module_imports_str}\n"

    compiled_code = [header]

    # Generate weakref import if there are wrapped classes
    if wrapped_classes:
        weakref_import = _generate_weakref_import(wrapped_classes)
        compiled_code.append(weakref_import)
        compiled_code.append("")  # Add blank line after import

    # Separate classes and functions to ensure correct ordering
    # Classes must be compiled before functions to avoid forward reference issues
    classes = []
    functions = []

    for o, (target_module, target_name) in module_items.items():
        obj_module = o.__module__
        if isinstance(o, type):
            classes.append((o, obj_module))
        elif isinstance(o, types.FunctionType):
            functions.append((o, obj_module))

    # Compile all classes first
    for cls, obj_module in classes:
        code = compile_class(
            cls,
            obj_module,
            synchronizer,
            _all_wrapped_classes=all_wrapped_classes,
            _local_wrapped_classes=wrapped_classes,
            _cross_module_imports=cross_module_imports,
        )
        compiled_code.append(code)

    # Then compile all functions
    for func, obj_module in functions:
        code = compile_function(
            func,
            obj_module,
            synchronizer,
            _all_wrapped_classes=all_wrapped_classes,
            _local_wrapped_classes=wrapped_classes,
            _cross_module_imports=cross_module_imports,
        )
        compiled_code.append(code)
        compiled_code.append("")  # Add blank line after function

    return "\n".join(compiled_code)


def compile_modules(synchronizer: Synchronizer) -> dict[str, str]:
    """
    Compile wrapped items into separate module files.

    Args:
        synchronizer: The Synchronizer instance

    Returns:
        Dict mapping module names to their generated code
    """
    wrapped_items = synchronizer._wrapped

    # Group items by target module to get the list of modules we need to generate
    modules = {}
    for obj, (target_module, target_name) in wrapped_items.items():
        if target_module not in modules:
            modules[target_module] = {}
        modules[target_module][obj] = (target_module, target_name)

    # Compile each module
    result = {}
    for module_name in sorted(modules.keys()):
        code = compile_module(module_name, synchronizer)
        if code:
            result[module_name] = code

    return result
