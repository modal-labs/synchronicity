"""Main compilation module - imports from codegen package and provides compile_* functions."""

import inspect
import sys
import types

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


def _generate_wrapper_helpers(wrapped_classes: dict[str, str], impl_module: str) -> str:
    """
    Generate wrapper helper functions for each wrapped class.

    Each helper maintains a WeakValueDictionary cache to preserve identity
    (same impl instance always returns the same wrapper instance).

    Args:
        wrapped_classes: Mapping of wrapper names to impl qualified names
        impl_module: The implementation module name

    Returns:
        String containing all wrapper helper function definitions
    """
    if not wrapped_classes:
        return ""

    helpers = []

    # Import weakref
    helpers.append("import weakref")
    helpers.append("")

    # Generate a helper for each wrapped class
    for wrapper_name, impl_qualified in wrapped_classes.items():
        helper_code = f"""# Wrapper cache for {wrapper_name} to preserve identity
_cache_{wrapper_name}: weakref.WeakValueDictionary = weakref.WeakValueDictionary()

def _wrap_{wrapper_name}(impl_instance: {impl_qualified}) -> "{wrapper_name}":
    \"\"\"Wrap an implementation instance, preserving identity via weak reference cache.\"\"\"
    # Use id() as cache key since impl instances are Python objects
    cache_key = id(impl_instance)

    # Check cache first
    if cache_key in _cache_{wrapper_name}:
        return _cache_{wrapper_name}[cache_key]

    # Create new wrapper using __new__ to bypass __init__
    wrapper = {wrapper_name}.__new__({wrapper_name})
    wrapper._impl_instance = impl_instance

    # Cache it
    _cache_{wrapper_name}[cache_key] = wrapper

    return wrapper"""
        helpers.append(helper_code)

    return "\n\n".join(helpers)


def compile_function(
    f: types.FunctionType,
    target_module: str,
    synchronizer_name: str,
    wrapped_classes: dict[str, str] = None,
) -> str:
    """
    Compile a function into a wrapper class that provides both sync and async versions.
    Uses the decorator pattern similar to method wrapping.

    Args:
        f: The function to compile
        target_module: The module name where the original function is located
        synchronizer_name: The name of the synchronizer to use
        wrapped_classes: Mapping of wrapper names to impl qualified names for type translation

    Returns:
        String containing the generated wrapper class and decorated function code
    """
    if wrapped_classes is None:
        wrapped_classes = {}

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
            wrapper_type, impl_type = translate_type_annotation(
                param.annotation, wrapped_classes, target_module
            )
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
                sync_return_str = f" -> typing.Generator[{wrapper_yield_type}, None, None]"
                if len(return_annotation.__args__) > 1:
                    send_type = return_annotation.__args__[1]
                    send_type_str = format_type_annotation(send_type)
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
            # For descriptor class methods, quote wrapped class names to handle forward references
            # For final function, use unquoted names since all classes are defined by then
            quoted_wrapper_type = wrapper_return_type
            for wrapper_name in wrapped_classes.keys():
                # Quote standalone wrapped class names in descriptor
                if wrapper_name == wrapper_return_type:
                    quoted_wrapper_type = f'"{wrapper_name}"'
                    break
            # Descriptor class methods use quoted types
            sync_return_str_descriptor = f" -> {quoted_wrapper_type}"
            async_return_str_descriptor = f" -> {quoted_wrapper_type}"
            # Final function uses unquoted types
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
            wrap_expr = build_wrap_expr(yield_type, wrapped_classes, "item")
            aio_body = f"""        gen = impl_function({call_args_str})
        async for item in self._synchronizer._run_generator_async(gen):
            yield {wrap_expr}"""
        else:
            aio_body = f"""        gen = impl_function({call_args_str})
        async for item in self._synchronizer._run_generator_async(gen):
            yield item"""
    else:
        # For regular async functions
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(return_annotation, wrapped_classes, "result")
            aio_body = f"""        result = await impl_function({call_args_str})
        return {wrap_expr}"""
        else:
            aio_body = f"""        return await impl_function({call_args_str})"""

    # Build unwrap section for aio() if needed
    aio_impl_ref = f"        impl_function = {target_module}.{f.__name__}"
    aio_unwrap = f"\n{aio_impl_ref}"
    if unwrap_code:
        # Adjust indentation for aio method (8 spaces)
        aio_unwrap_lines = [line.replace("    ", "        ", 1) for line in unwrap_stmts]
        aio_unwrap += "\n" + "\n".join(aio_unwrap_lines)

    # Build unwrap section for __call__ if needed - uses original call_args_str
    # which has the wrapper parameter names, not the impl ones
    call_unwrap = ""
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
            wrap_expr = build_wrap_expr(yield_type, wrapped_classes, "item")
            sync_gen_body = f"""    gen = impl_function({call_args_str})
    for item in get_synchronizer('{synchronizer_name}')._run_generator_sync(gen):
        yield {wrap_expr}"""
        else:
            sync_gen_body = f"""    gen = impl_function({call_args_str})
    yield from get_synchronizer('{synchronizer_name}')._run_generator_sync(gen)"""
        sync_function_body = sync_gen_body
    else:
        # For regular async functions
        sync_runner = f"get_synchronizer('{synchronizer_name}')._run_function_sync"
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(return_annotation, wrapped_classes, "result")
            sync_function_body = f"""    result = {sync_runner}(impl_function({call_args_str}))
    return {wrap_expr}"""
        else:
            sync_function_body = f"""    return {sync_runner}(impl_function({call_args_str}))"""

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
    synchronizer_name: str,
    target_module: str,
    class_name: str,
    wrapped_classes: dict[str, str] = None,
) -> tuple[str, str]:
    """
    Compile a method wrapper class that provides both sync and async versions.

    This generates a ClassName_methodname style class that works with the @wrapped_method decorator.

    Args:
        method: The method to wrap
        method_name: The name of the method
        synchronizer_name: The name of the synchronizer to use
        target_module: The module where the original class is located
        class_name: The name of the class containing the method
        wrapped_classes: Mapping of wrapper names to impl qualified names for type translation

    Returns:
        Tuple of (wrapper_class_code, sync_method_code)
    """
    if wrapped_classes is None:
        wrapped_classes = {}

    # Get method signature and annotations
    sig = inspect.signature(method)
    return_annotation = sig.return_annotation

    # Parse parameters - we'll need to translate types
    params = []
    call_args = []
    unwrap_stmts = []

    for name, param in sig.parameters.items():
        if name == "self":
            continue

        # Translate the parameter type annotation
        if param.annotation != param.empty:
            wrapper_type, impl_type = translate_type_annotation(
                param.annotation, wrapped_classes, target_module
            )
            param_str = f"{name}: {wrapper_type}"

            # Generate unwrap code if needed
            if needs_translation(param.annotation, wrapped_classes):
                unwrap_expr = build_unwrap_expr(param.annotation, wrapped_classes, name)
                unwrap_stmts.append(f"        {name}_impl = {unwrap_expr}")
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
    is_async_gen = is_async_generator(method, return_annotation)

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
                sync_return_str = f" -> typing.Generator[{wrapper_yield_type}, None, None]"
                if len(return_annotation.__args__) > 1:
                    send_type = return_annotation.__args__[1]
                    send_type_str = format_type_annotation(send_type)
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
            # For descriptor class methods, quote wrapped class names to handle forward references
            # For final method, use unquoted names since all classes are defined by then
            quoted_wrapper_type = wrapper_return_type
            for wrapper_name in wrapped_classes.keys():
                # Quote standalone wrapped class names in descriptor
                if wrapper_name == wrapper_return_type:
                    quoted_wrapper_type = f'"{wrapper_name}"'
                    break
            # Descriptor class methods use quoted types
            sync_return_str_descriptor = f" -> {quoted_wrapper_type}"
            async_return_str_descriptor = f" -> {quoted_wrapper_type}"
            # Final method uses unquoted types
            sync_return_str = f" -> {wrapper_return_type}"
            async_return_str = f" -> {wrapper_return_type}"
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
            wrap_expr = build_wrap_expr(yield_type, wrapped_classes, "item")
            aio_body = f"""        gen = impl_function({impl_call_args})
        async for item in self._synchronizer._run_generator_async(gen):
            yield {wrap_expr}"""
        else:
            aio_body = f"""        gen = impl_function({impl_call_args})
        async for item in self._synchronizer._run_generator_async(gen):
            yield item"""
    else:
        # For regular async methods
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(return_annotation, wrapped_classes, "result")
            aio_body = f"""        result = await impl_function({impl_call_args})
        return {wrap_expr}"""
        else:
            aio_body = f"""        return await impl_function({impl_call_args})"""

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

    def __call__(self, {param_str}){sync_return_str_descriptor}:
        return self._unbound_sync_wrapper_method(self._wrapper_instance, {call_params})

    async def aio(self, {param_str}){async_return_str_descriptor}:{aio_unwrap}
{aio_body}
"""

    # Build the sync wrapper method code
    if is_async_gen:
        # For generators, wrap each yielded item
        if needs_return_wrap and hasattr(return_annotation, "__args__"):
            yield_type = return_annotation.__args__[0]
            wrap_expr = build_wrap_expr(yield_type, wrapped_classes, "item")
            sync_method_body = f"""        gen = impl_function({impl_call_args})
        for item in self._synchronizer._run_generator_sync(gen):
            yield {wrap_expr}"""
        else:
            sync_method_body = f"""        gen = impl_function({impl_call_args})
        yield from self._synchronizer._run_generator_sync(gen)"""
    else:
        # For regular async methods
        sync_runner = "self._synchronizer._run_function_sync"
        if needs_return_wrap:
            wrap_expr = build_wrap_expr(return_annotation, wrapped_classes, "result")
            sync_method_body = f"""        result = {sync_runner}(impl_function({impl_call_args}))
        return {wrap_expr}"""
        else:
            sync_method_body = f"""        return {sync_runner}(impl_function({impl_call_args}))"""

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
    cls: type, target_module: str, synchronizer_name: str, wrapped_classes: dict[str, str] = None
) -> str:
    """
    Compile a class into a wrapper class where all methods are wrapped with sync/async versions.

    Args:
        cls: The class to compile
        target_module: The module name where the original class is located
        synchronizer_name: The name of the synchronizer to use
        wrapped_classes: Mapping of wrapper names to impl qualified names for type translation

    Returns:
        String containing the generated wrapper class code
    """
    if wrapped_classes is None:
        wrapped_classes = {}

    # Get all async methods from the class
    methods = []
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if not name.startswith("_") and (
            inspect.iscoroutinefunction(method) or inspect.isasyncgenfunction(method)
        ):  # Only wrap async methods
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
            method, method_name, synchronizer_name, target_module, cls.__name__, wrapped_classes
        )
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

    wrapper_class_code = f"""class {cls.__name__}:
    \"\"\"Wrapper class for {target_module}.{cls.__name__} with sync/async method support\"\"\"

    _synchronizer = get_synchronizer('{synchronizer_name}')

    def __init__(self, {init_signature}):
        self._impl_instance = {target_module}.{cls.__name__}({init_call})

{properties_section}

{methods_section}"""

    # Combine all the code
    all_code = []
    all_code.extend(method_wrapper_classes)
    all_code.append("")  # Add blank line before main class
    all_code.append(wrapper_class_code)

    return "\n".join(all_code)


def compile_library(wrapped_items: dict, synchronizer_name: str) -> str:
    """
    Compile all wrapped items in a library.

    Args:
        wrapped_items: Dict mapping original objects to (target_module, target_name) tuples
        synchronizer_name: The name of the synchronizer to use

    Returns:
        String containing all compiled wrapper code
    """
    # Collect all unique implementation modules
    impl_modules = set()
    for o, (target_module, target_name) in wrapped_items.items():
        impl_modules.add(o.__module__)

    if not impl_modules:
        return ""

    # Use the first module as the primary impl_module (for backward compatibility)
    impl_module = sorted(impl_modules)[0]

    # Extract wrapped classes mapping for type translation
    wrapped_classes = get_wrapped_classes(wrapped_items)

    # Generate header with imports for all implementation modules
    imports = "\n".join(f"import {mod}" for mod in sorted(impl_modules))
    header = f"""import typing

{imports}

from synchronicity2.descriptor import wrapped_function, wrapped_method
from synchronicity2.synchronizer import get_synchronizer
"""

    compiled_code = [header]

    # Generate wrapper helper functions if there are wrapped classes
    if wrapped_classes:
        wrapper_helpers = _generate_wrapper_helpers(wrapped_classes, impl_module)
        compiled_code.append(wrapper_helpers)
        compiled_code.append("")  # Add blank line after helpers

    # Separate classes and functions to ensure correct ordering
    # Classes must be compiled before functions to avoid forward reference issues
    classes = []
    functions = []

    for o, (target_module, target_name) in wrapped_items.items():
        obj_module = o.__module__
        if isinstance(o, type):
            classes.append((o, obj_module))
        elif isinstance(o, types.FunctionType):
            functions.append((o, obj_module))

    # Compile all classes first
    for cls, obj_module in classes:
        code = compile_class(cls, obj_module, synchronizer_name, wrapped_classes)
        compiled_code.append(code)

    # Then compile all functions
    for func, obj_module in functions:
        code = compile_function(func, obj_module, synchronizer_name, wrapped_classes)
        compiled_code.append(code)
        compiled_code.append("")  # Add blank line after function

    return "\n".join(compiled_code)
