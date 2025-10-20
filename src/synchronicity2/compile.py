"""Main compilation module - imports from codegen package and provides compile_* functions."""

from __future__ import annotations

import inspect
import types
from typing import TYPE_CHECKING

from .codegen import (
    build_unwrap_expr,
    build_wrap_expr,
    format_return_types,
    format_type_for_annotation,
    is_async_generator,
    needs_translation,
    parse_parameters,
)

if TYPE_CHECKING:
    from .synchronizer import Synchronizer


# Old helper functions removed - now using object-based type translation


def compile_function(
    f: types.FunctionType,
    synchronizer: Synchronizer,
) -> str:
    """
    Compile a function into a wrapper class that provides both sync and async versions.
    Uses the decorator pattern similar to method wrapping.

    Args:
        f: The function to compile
        synchronizer: The Synchronizer instance

    Returns:
        String containing the generated wrapper class and decorated function code
    """
    synchronizer_name = synchronizer._name
    origin_module = f.__module__  # The implementation module where f is defined

    # Get the target (output) module for this function from the synchronizer
    if f not in synchronizer._wrapped:
        raise ValueError(
            f"Function {f.__name__} from module {origin_module} is not in the synchronizer's "
            f"wrapped dict. Only functions registered with the synchronizer can be compiled."
        )
    current_target_module, _ = synchronizer._wrapped[f]

    # Use get_annotations to resolve all type annotations to type objects
    # This allows us to use object identity checks instead of string comparisons
    annotations = inspect.get_annotations(f, eval_str=True)

    # Get function signature
    sig = inspect.signature(f)
    return_annotation = annotations.get("return", sig.return_annotation)

    # Parse parameters - we'll need to translate types
    params = []
    call_args = []
    unwrap_stmts = []

    for name, param in sig.parameters.items():
        # Get resolved annotation for this parameter
        param_annotation = annotations.get(name, param.annotation)

        # Translate the parameter type annotation
        if param_annotation != param.empty:
            wrapper_type_str = format_type_for_annotation(param_annotation, synchronizer, current_target_module)
            param_str = f"{name}: {wrapper_type_str}"

            # Generate unwrap code if needed
            if needs_translation(param_annotation, synchronizer):
                unwrap_expr = build_unwrap_expr(param_annotation, synchronizer, name)
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
        if needs_translation(return_annotation, synchronizer):
            wrapper_return_type = format_type_for_annotation(return_annotation, synchronizer, current_target_module)
            wrap_expr = build_wrap_expr(return_annotation, synchronizer, current_target_module, "result")
            function_body = f"""    result = impl_function({call_args_str})
    return {wrap_expr}"""
            # Quote entire annotation when it contains wrapper types
            return_str = f' -> "{wrapper_return_type}"'
        else:
            # Format return type if available
            if return_annotation != inspect.Signature.empty:
                return_str = f" -> {format_type_for_annotation(return_annotation, synchronizer, current_target_module)}"
            else:
                return_str = ""
            function_body = f"""    return impl_function({call_args_str})"""

        # Add impl_function reference and unwrap statements
        impl_ref = f"    impl_function = {origin_module}.{f.__name__}"
        if unwrap_code:
            function_body = f"{impl_ref}\n{unwrap_code}\n{function_body}"
        else:
            function_body = f"{impl_ref}\n{function_body}"

        # Generate simple function (no decorator, no wrapper class)
        return f"""def {f.__name__}({param_str}){return_str}:
{function_body}"""

    # Format return types - translate them
    if needs_translation(return_annotation, synchronizer):
        wrapper_return_type = format_type_for_annotation(return_annotation, synchronizer, current_target_module)

        if is_async_gen:
            # Extract yield type from AsyncGenerator
            import typing

            args = typing.get_args(return_annotation)
            if args:
                yield_type = args[0]
                wrapper_yield_type = format_type_for_annotation(yield_type, synchronizer, current_target_module)

                # Quote wrapped class names in generic types for forward references
                # Always quote the entire annotation if it contains wrapper types
                if isinstance(yield_type, type) and yield_type in synchronizer._wrapped:
                    # It's a wrapped type - quote entire Generator annotation
                    sync_return_str = f' -> "typing.Generator[{wrapper_yield_type}, None, None]"'
                    if len(args) > 1:
                        send_type = args[1]
                        send_type_str = format_type_for_annotation(send_type, synchronizer, current_target_module)
                        async_return_str = f' -> "typing.AsyncGenerator[{wrapper_yield_type}, {send_type_str}]"'
                    else:
                        async_return_str = f' -> "typing.AsyncGenerator[{wrapper_yield_type}]"'
                else:
                    # Not a wrapped type - don't quote
                    sync_return_str = f" -> typing.Generator[{wrapper_yield_type}, None, None]"
                    if len(args) > 1:
                        send_type = args[1]
                        send_type_str = format_type_for_annotation(send_type, synchronizer, current_target_module)
                        async_return_str = f" -> typing.AsyncGenerator[{wrapper_yield_type}, {send_type_str}]"
                    else:
                        async_return_str = f" -> typing.AsyncGenerator[{wrapper_yield_type}]"
            else:
                sync_return_str = " -> typing.Generator"
                async_return_str = " -> typing.AsyncGenerator"
            # For generators, descriptor and final function have the same return type
            sync_return_str_descriptor = sync_return_str
            async_return_str_descriptor = async_return_str
        else:
            # For regular functions with wrapped return types
            # Always quote the entire annotation if it contains wrapper types
            sync_return_str_descriptor = f' -> "{wrapper_return_type}"'
            async_return_str_descriptor = f' -> "{wrapper_return_type}"'
            sync_return_str = f' -> "{wrapper_return_type}"'
            async_return_str = f' -> "{wrapper_return_type}"'
    else:
        sync_return_str, async_return_str = format_return_types(return_annotation, is_async_gen)
        sync_return_str_descriptor = sync_return_str
        async_return_str_descriptor = async_return_str

    # Generate the wrapper class
    wrapper_class_name = f"_{f.__name__}"

    # Determine if we need to wrap the return value
    needs_return_wrap = needs_translation(return_annotation, synchronizer)

    # Build the aio() method body
    if is_async_gen:
        # For generators, wrap each yielded item
        if needs_return_wrap:
            import typing

            args = typing.get_args(return_annotation)
            if args:
                yield_type = args[0]
                wrap_expr = build_wrap_expr(yield_type, synchronizer, current_target_module, "item")
                aio_body = f"""        gen = impl_function({call_args_str})
        async for item in self._synchronizer._run_generator_async(gen):
            yield {wrap_expr}"""
            else:
                aio_body = f"""        gen = impl_function({call_args_str})
        async for item in self._synchronizer._run_generator_async(gen):
            yield item"""
        else:
            aio_body = f"""        gen = impl_function({call_args_str})
        async for item in self._synchronizer._run_generator_async(gen):
            yield item"""
    elif is_async_func:
        # For regular async functions
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(return_annotation, synchronizer, current_target_module, "result")
            aio_body = f"""        result = await impl_function({call_args_str})
        return {wrap_expr}"""
        else:
            aio_body = f"""        return await impl_function({call_args_str})"""
    else:
        # For non-async functions, call directly (no await, no synchronizer)
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(return_annotation, synchronizer, current_target_module, "result")
            aio_body = f"""        result = impl_function({call_args_str})
        return {wrap_expr}"""
        else:
            aio_body = f"""        return impl_function({call_args_str})"""

    # Build unwrap section for aio() if needed
    aio_impl_ref = f"        impl_function = {origin_module}.{f.__name__}"
    aio_unwrap = f"\n{aio_impl_ref}"
    if unwrap_code:
        # Adjust indentation for aio method (8 spaces)
        aio_unwrap_lines = [line.replace("    ", "        ", 1) for line in unwrap_stmts]
        aio_unwrap += "\n" + "\n".join(aio_unwrap_lines)

    wrapper_class_code = f"""class {wrapper_class_name}:
    _synchronizer = get_synchronizer('{synchronizer_name}')
    _impl_function = {origin_module}.{f.__name__}
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
        if needs_return_wrap:
            import typing

            args = typing.get_args(return_annotation)
            if args:
                yield_type = args[0]
                wrap_expr = build_wrap_expr(yield_type, synchronizer, current_target_module, "item")
                sync_gen_body = f"""    gen = impl_function({call_args_str})
    for item in get_synchronizer('{synchronizer_name}')._run_generator_sync(gen):
        yield {wrap_expr}"""
            else:
                sync_gen_body = f"""    gen = impl_function({call_args_str})
    yield from get_synchronizer('{synchronizer_name}')._run_generator_sync(gen)"""
        else:
            sync_gen_body = f"""    gen = impl_function({call_args_str})
    yield from get_synchronizer('{synchronizer_name}')._run_generator_sync(gen)"""
        sync_function_body = sync_gen_body
    elif is_async_func:
        # For regular async functions, use synchronizer
        sync_runner = f"get_synchronizer('{synchronizer_name}')._run_function_sync"
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(return_annotation, synchronizer, current_target_module, "result")
            sync_function_body = f"""    result = {sync_runner}(impl_function({call_args_str}))
    return {wrap_expr}"""
        else:
            sync_function_body = f"""    return {sync_runner}(impl_function({call_args_str}))"""
    else:
        # For non-async functions, call directly without synchronizer
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(return_annotation, synchronizer, current_target_module, "result")
            sync_function_body = f"""    result = impl_function({call_args_str})
    return {wrap_expr}"""
        else:
            sync_function_body = f"""    return impl_function({call_args_str})"""

    # Add impl_function reference and unwrap statements to sync function if needed
    impl_ref = f"    impl_function = {origin_module}.{f.__name__}"
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
    origin_module: str,
    class_name: str,
    current_target_module: str,
) -> tuple[str, str]:
    """
    Compile a method wrapper class that provides both sync and async versions.

    This generates a ClassName_methodname style class that works with the @wrapped_method decorator.

    Args:
        method: The method to wrap
        method_name: The name of the method
        synchronizer: The Synchronizer instance
        origin_module: The module where the original class is defined
        class_name: The name of the class containing the method
        current_target_module: The target module for the wrapper (provided by compile_class)

    Returns:
        Tuple of (wrapper_class_code, sync_method_code)
    """
    synchronizer_name = synchronizer._name

    # Use get_annotations to resolve all type annotations to type objects
    annotations = inspect.get_annotations(method, eval_str=True)

    # Get method signature
    sig = inspect.signature(method)
    return_annotation = annotations.get("return", sig.return_annotation)

    # Parse parameters - we'll need to translate types
    params = []
    params_descriptor = []  # For wrapper class __call__, with quoted wrapped types
    call_args = []
    unwrap_stmts = []

    for name, param in sig.parameters.items():
        if name == "self":
            continue

        # Get resolved annotation for this parameter
        param_annotation = annotations.get(name, param.annotation)

        # Translate the parameter type annotation
        if param_annotation != param.empty:
            wrapper_type_str = format_type_for_annotation(param_annotation, synchronizer, current_target_module)
            param_str = f"{name}: {wrapper_type_str}"

            # For descriptor __call__, quote wrapped class names for forward references
            if isinstance(param_annotation, type) and param_annotation in synchronizer._wrapped:
                param_str_descriptor = f'{name}: "{wrapper_type_str}"'
            else:
                param_str_descriptor = param_str

            # Generate unwrap code if needed
            if needs_translation(param_annotation, synchronizer):
                unwrap_expr = build_unwrap_expr(param_annotation, synchronizer, name)
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

    # Check if it's a non-async method (rare, but possible)
    is_async = inspect.iscoroutinefunction(method) or is_async_gen

    # If not async at all, return empty strings (no wrapper needed)
    if not is_async:
        return "", ""

    # Format return types - translate them
    if needs_translation(return_annotation, synchronizer):
        wrapper_return_type = format_type_for_annotation(return_annotation, synchronizer, current_target_module)

        if is_async_gen:
            # Extract yield type from AsyncGenerator
            import typing

            args = typing.get_args(return_annotation)
            if args:
                yield_type = args[0]
                wrapper_yield_type = format_type_for_annotation(yield_type, synchronizer, current_target_module)

                # Quote wrapped class names in generic types for forward references
                # Check both direct types and ForwardRef
                should_quote = False
                if isinstance(yield_type, type) and yield_type in synchronizer._wrapped:
                    should_quote = True
                elif hasattr(yield_type, "__forward_arg__"):
                    # ForwardRef - check if it refers to a wrapped class
                    forward_str = yield_type.__forward_arg__
                    for obj in synchronizer._wrapped.keys():
                        if isinstance(obj, type) and obj.__name__ == forward_str:
                            should_quote = True
                            break

                if should_quote:
                    quoted_yield_type = f'"{wrapper_yield_type}"'
                else:
                    quoted_yield_type = wrapper_yield_type

                # For the actual method definitions, quote the entire type if it contains wrapper types
                # to avoid forward reference issues at class definition time
                if should_quote:
                    sync_return_str = f' -> "typing.Generator[{wrapper_yield_type}, None, None]"'
                else:
                    sync_return_str = f" -> typing.Generator[{quoted_yield_type}, None, None]"

                if len(args) > 1:
                    send_type = args[1]
                    send_type_str = format_type_for_annotation(send_type, synchronizer, current_target_module)
                    if should_quote:
                        async_return_str = f' -> "typing.AsyncGenerator[{wrapper_yield_type}, {send_type_str}]"'
                    else:
                        async_return_str = f" -> typing.AsyncGenerator[{quoted_yield_type}, {send_type_str}]"
                else:
                    if should_quote:
                        async_return_str = f' -> "typing.AsyncGenerator[{wrapper_yield_type}]"'
                    else:
                        async_return_str = f" -> typing.AsyncGenerator[{quoted_yield_type}]"
            else:
                sync_return_str = " -> typing.Generator"
                async_return_str = " -> typing.AsyncGenerator"
            # For descriptor classes, use the same (already safe with quotes inside generics)
            sync_return_str_descriptor = sync_return_str
            async_return_str_descriptor = async_return_str
        else:
            # For regular methods with wrapped return types
            # Always quote the entire type annotation if it contains wrapper types
            if isinstance(return_annotation, type) and return_annotation in synchronizer._wrapped:
                # Direct wrapped class - quote entire annotation for safety
                sync_return_str_descriptor = f' -> "{wrapper_return_type}"'
                async_return_str_descriptor = f' -> "{wrapper_return_type}"'
                sync_return_str = f' -> "{wrapper_return_type}"'
                async_return_str = f' -> "{wrapper_return_type}"'
            elif needs_translation(return_annotation, synchronizer):
                # Complex type containing wrapper types - quote entire annotation
                sync_return_str_descriptor = f' -> "{wrapper_return_type}"'
                async_return_str_descriptor = f' -> "{wrapper_return_type}"'
                sync_return_str = f' -> "{wrapper_return_type}"'
                async_return_str = f' -> "{wrapper_return_type}"'
            else:
                # No wrapper types - safe to not quote
                sync_return_str_descriptor = f" -> {wrapper_return_type}"
                async_return_str_descriptor = f" -> {wrapper_return_type}"
                sync_return_str = f" -> {wrapper_return_type}"
                async_return_str = f" -> {wrapper_return_type}"
    else:
        sync_return_str, async_return_str = format_return_types(return_annotation, is_async_gen)
        sync_return_str_descriptor = sync_return_str
        async_return_str_descriptor = async_return_str

    # Generate the wrapper class
    wrapper_class_name = f"{class_name}_{method_name}"

    # Determine if we need to wrap the return value
    needs_return_wrap = needs_translation(return_annotation, synchronizer)

    # Build the aio() method body
    if is_async_gen:
        # For generators, wrap each yielded item
        if needs_return_wrap:
            import typing

            args = typing.get_args(return_annotation)
            if args:
                yield_type = args[0]
                wrap_expr = build_wrap_expr(yield_type, synchronizer, current_target_module, "item")
                aio_body = f"""        async for item in impl_method(self._wrapper_instance._impl_instance, {call_args_str}):
            yield {wrap_expr}"""
            else:
                aio_body = f"""        async for item in impl_method(self._wrapper_instance._impl_instance, {call_args_str}):
            yield item"""
        else:
            aio_body = f"""        async for item in impl_method(self._wrapper_instance._impl_instance, {call_args_str}):
            yield item"""
    else:
        # For regular async methods
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(return_annotation, synchronizer, current_target_module, "result")
            aio_body = f"""        result = await impl_method(self._wrapper_instance._impl_instance, {call_args_str})
        return {wrap_expr}"""
        else:
            aio_body = f"""        return await impl_method(self._wrapper_instance._impl_instance, {call_args_str})"""

    # Build unwrap section for aio() if needed
    aio_impl_ref = f"        impl_method = {origin_module}.{class_name}.{method_name}"
    aio_unwrap = f"\n{aio_impl_ref}"
    if unwrap_code:
        aio_unwrap += "\n" + unwrap_code

    wrapper_class_code = f"""class {wrapper_class_name}:
    def __init__(self, wrapper_instance, unbound_sync_wrapper_method: typing.Callable[..., typing.Any]):
        self._wrapper_instance = wrapper_instance
        self._unbound_sync_wrapper_method = unbound_sync_wrapper_method

    def __call__(self, {param_str_descriptor}){sync_return_str_descriptor}:
        return self._unbound_sync_wrapper_method(self._wrapper_instance, {", ".join([p.split(":")[0].split("=")[0].strip() for p in params])})

    async def aio(self, {param_str_descriptor}){async_return_str_descriptor}:{aio_unwrap}
{aio_body}
"""

    # Build the sync wrapper method code
    if is_async_gen:
        # For generators, wrap each yielded item
        if needs_return_wrap:
            import typing

            args = typing.get_args(return_annotation)
            if args:
                yield_type = args[0]
                wrap_expr = build_wrap_expr(yield_type, synchronizer, current_target_module, "item")
                sync_method_body = f"""        gen = impl_method(self._impl_instance, {call_args_str})
        for item in self._synchronizer._run_generator_sync(gen):
            yield {wrap_expr}"""
            else:
                sync_method_body = f"""        gen = impl_method(self._impl_instance, {call_args_str})
        yield from self._synchronizer._run_generator_sync(gen)"""
        else:
            sync_method_body = f"""        gen = impl_method(self._impl_instance, {call_args_str})
        yield from self._synchronizer._run_generator_sync(gen)"""
    else:
        # For regular async methods
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(return_annotation, synchronizer, current_target_module, "result")
            sync_method_body = f"""        result = self._synchronizer._run_function_sync(impl_method(self._impl_instance, {call_args_str}))
        return {wrap_expr}"""
        else:
            sync_method_body = f"""        return self._synchronizer._run_function_sync(impl_method(self._impl_instance, {call_args_str}))"""

    # Add impl_method reference and unwrap statements
    impl_ref = f"        impl_method = {origin_module}.{class_name}.{method_name}"
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
    synchronizer: Synchronizer,
) -> str:
    """
    Compile a class into a wrapper class where all methods are wrapped with sync/async versions.

    Args:
        cls: The class to compile
        synchronizer: The Synchronizer instance

    Returns:
        String containing the generated wrapper class code
    """
    synchronizer_name = synchronizer._name
    origin_module = cls.__module__  # The implementation module where cls is defined

    # Get the target (output) module for this class from the synchronizer
    if cls not in synchronizer._wrapped:
        raise ValueError(
            f"Class {cls.__name__} from module {origin_module} is not in the synchronizer's "
            f"wrapped dict. Only classes registered with the synchronizer can be compiled."
        )
    current_target_module, _ = synchronizer._wrapped[cls]

    # Get all methods from the class (both async and non-async)
    methods = []
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if not name.startswith("_"):
            # Wrap all public methods (async and non-async)
            methods.append((name, method))

    # Get class attributes from annotations - use get_annotations to resolve types
    attributes = []
    class_annotations = inspect.get_annotations(cls, eval_str=True)
    for name, annotation in class_annotations.items():
        if not name.startswith("_"):
            attr_type = format_type_for_annotation(annotation, synchronizer, current_target_module)
            attributes.append((name, attr_type))

    # Generate method wrapper classes and method code
    method_wrapper_classes = []
    method_definitions = []

    for method_name, method in methods:
        wrapper_class_code, sync_method_code = compile_method_wrapper(
            method,
            method_name,
            synchronizer,
            origin_module,
            cls.__name__,
            current_target_module,
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

    wrapper_class_code = f"""class {cls.__name__}:
    \"\"\"Wrapper class for {origin_module}.{cls.__name__} with sync/async method support\"\"\"

    _synchronizer = get_synchronizer('{synchronizer_name}')
    _instance_cache: weakref.WeakValueDictionary = weakref.WeakValueDictionary()

    def __init__(self, {init_signature}):
        self._impl_instance = {origin_module}.{cls.__name__}({init_call})

{from_impl_method}

{properties_section}

{methods_section}"""

    # Combine all the code
    all_code = []
    all_code.extend(method_wrapper_classes)
    all_code.append("")  # Add blank line before main class
    all_code.append(wrapper_class_code)

    return "\n".join(all_code)


def _get_cross_module_imports_new(
    module_name: str,
    module_items: dict,
    synchronizer: Synchronizer,
) -> dict[str, set[str]]:
    """
    Detect which wrapped classes from other modules are referenced in this module.

    Uses object identity checks against synchronizer._wrapped for robustness.

    Args:
        module_name: The current module being compiled
        module_items: Items in the current module
        synchronizer: The Synchronizer instance

    Returns:
        Dict mapping target module names to sets of wrapper class names
    """
    cross_module_refs = {}  # target_module -> set of class names

    # Check each item in this module for references to wrapped classes from other modules
    for obj, (target_module, target_name) in module_items.items():
        # Get signature if it's a function or class with methods
        if isinstance(obj, types.FunctionType):
            try:
                # Use get_annotations to resolve string annotations
                annotations = inspect.get_annotations(obj, eval_str=True)
                for param_name, annotation in annotations.items():
                    _check_annotation_for_cross_refs_new(annotation, module_name, synchronizer, cross_module_refs)
            except (NameError, AttributeError, TypeError):
                # If get_annotations fails, skip this function
                # In the new approach we don't fall back to string-based checks
                pass
        elif isinstance(obj, type):
            # Check methods of the class
            for method_name, method in inspect.getmembers(obj, predicate=inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                try:
                    # Try to use get_annotations to resolve string annotations
                    annotations = inspect.get_annotations(method, eval_str=True)
                    for annotation in annotations.values():
                        _check_annotation_for_cross_refs_new(annotation, module_name, synchronizer, cross_module_refs)
                except (NameError, AttributeError, TypeError, ValueError):
                    # If get_annotations fails, skip this method
                    pass

    return cross_module_refs


def _check_annotation_for_cross_refs_new(
    annotation,
    current_module: str,
    synchronizer: Synchronizer,
    cross_module_refs: dict,
) -> None:
    """Check a type annotation for references to wrapped classes from other modules using object identity."""
    # Handle direct class references
    if isinstance(annotation, type) and annotation in synchronizer._wrapped:
        target_module, wrapper_name = synchronizer._wrapped[annotation]
        if target_module != current_module:
            if target_module not in cross_module_refs:
                cross_module_refs[target_module] = set()
            cross_module_refs[target_module].add(wrapper_name)

    # Handle generic types (e.g., List[WrapperClass], Optional[WrapperClass])
    import typing

    args = typing.get_args(annotation)
    if args:
        for arg in args:
            _check_annotation_for_cross_refs_new(arg, current_module, synchronizer, cross_module_refs)


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

    # Check if there are any wrapped classes (for weakref import)
    has_wrapped_classes = any(isinstance(o, type) for o in module_items.keys())

    # Detect cross-module references using object-based approach
    cross_module_imports = _get_cross_module_imports_new(module_name, module_items, synchronizer)

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
    if has_wrapped_classes:
        compiled_code.append("import weakref")
        compiled_code.append("")  # Add blank line after import

    # Separate classes and functions to ensure correct ordering
    # Classes must be compiled before functions to avoid forward reference issues
    classes = []
    functions = []

    for o, (target_module, target_name) in module_items.items():
        if isinstance(o, type):
            classes.append(o)
        elif isinstance(o, types.FunctionType):
            functions.append(o)

    # Compile all classes first
    for cls in classes:
        code = compile_class(cls, synchronizer)
        compiled_code.append(code)

    # Then compile all functions
    for func in functions:
        code = compile_function(func, synchronizer)
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
