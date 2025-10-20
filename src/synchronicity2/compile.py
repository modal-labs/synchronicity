import collections.abc
import inspect
import sys
import types
import typing


def _format_type_annotation(annotation) -> str:
    """Format a type annotation for code generation."""
    if annotation is type(None):
        return "NoneType"

    if hasattr(annotation, "__origin__"):
        # This is a generic type like list[str], dict[str, int], etc.
        return repr(annotation).replace("typing.", "typing.")
    elif hasattr(annotation, "__module__") and hasattr(annotation, "__name__"):
        if annotation.__module__ in ("builtins", "__builtin__"):
            return annotation.__name__
        else:
            return f"{annotation.__module__}.{annotation.__name__}"
    else:
        return repr(annotation)


def _parse_parameters(sig: inspect.Signature, skip_self: bool = False) -> tuple[str, str, list[str]]:
    """
    Parse function/method parameters into formatted strings.

    Args:
        sig: The function signature
        skip_self: If True, skip 'self' parameter (for methods)

    Returns:
        Tuple of (params_str, call_args_str, call_args_list):
        - params_str: Comma-separated parameter declarations with types
        - call_args_str: Comma-separated parameter names for calls
        - call_args_list: List of parameter names
    """
    params = []
    call_args = []

    for name, param in sig.parameters.items():
        if skip_self and name == "self":
            continue

        param_str = name
        if param.annotation != param.empty:
            annotation_str = _format_type_annotation(param.annotation)
            param_str += f": {annotation_str}"

        if param.default is not param.empty:
            default_val = repr(param.default)
            param_str += f" = {default_val}"

        params.append(param_str)
        call_args.append(name)

    params_str = ", ".join(params)
    call_args_str = ", ".join(call_args)

    return params_str, call_args_str, call_args


def _is_async_generator(func_or_method, return_annotation) -> bool:
    """
    Check if a callable is an async generator.

    Args:
        func_or_method: The function or method to check
        return_annotation: The return type annotation

    Returns:
        True if the callable is an async generator
    """
    # First check using inspect
    if inspect.isasyncgenfunction(func_or_method):
        return True

    # Also check return annotation
    if return_annotation != inspect.Signature.empty:
        return (
            hasattr(return_annotation, "__origin__") and return_annotation.__origin__ is collections.abc.AsyncGenerator
        )

    return False


def _format_return_types(return_annotation, is_async_generator: bool) -> tuple[str, str]:
    """
    Format sync and async return type strings.

    Args:
        return_annotation: The return type annotation from the function signature
        is_async_generator: Whether the function is an async generator

    Returns:
        Tuple of (sync_return_str, async_return_str) including " -> " prefix,
        or empty strings if no return annotation
    """
    if return_annotation == inspect.Signature.empty:
        if is_async_generator:
            return " -> typing.Generator", " -> typing.AsyncGenerator"
        else:
            return "", ""

    # Handle different return types
    if is_async_generator:
        # For async generators, sync version returns Generator[T, None, None],
        # async version returns AsyncGenerator[T, None]
        if hasattr(return_annotation, "__args__") and return_annotation.__args__:
            # Extract the yielded type from AsyncGenerator[T, Send]
            yield_type = return_annotation.__args__[0]
            yield_type_str = _format_type_annotation(yield_type)
            sync_return_annotation = f"typing.Generator[{yield_type_str}, None, None]"

            # For async generators, also extract the send type (usually None) for proper typing
            if len(return_annotation.__args__) > 1:
                send_type = return_annotation.__args__[1]
                send_type_str = _format_type_annotation(send_type)
                async_return_annotation = f"typing.AsyncGenerator[{yield_type_str}, {send_type_str}]"
            else:
                async_return_annotation = f"typing.AsyncGenerator[{yield_type_str}]"
        else:
            sync_return_annotation = "typing.Generator"
            async_return_annotation = "typing.AsyncGenerator"
    else:
        # For regular async functions
        sync_return_annotation = _format_type_annotation(return_annotation)
        async_return_annotation = sync_return_annotation

    sync_return_str = f" -> {sync_return_annotation}"
    async_return_str = f" -> {async_return_annotation}"

    return sync_return_str, async_return_str


# ============================================================================
# Type Translation Utilities
# ============================================================================


def _get_wrapped_classes(wrapped_items: dict) -> dict[str, str]:
    """
    Extract mapping of wrapped class names to their fully-qualified implementation names.

    Args:
        wrapped_items: Dict mapping original objects to (target_module, target_name) tuples

    Returns:
        Dict mapping wrapper class name to implementation qualified name.
        Example: {"Bar": "_my_library.Bar", "Baz": "_my_library.Baz"}
    """
    wrapped = {}
    for obj, (target_module, target_name) in wrapped_items.items():
        if isinstance(obj, type):  # It's a class
            impl_qualified = f"{obj.__module__}.{obj.__name__}"
            wrapped[target_name] = impl_qualified
    return wrapped


def _translate_type_annotation(
    annotation, wrapped_classes: dict[str, str], impl_module: str
) -> tuple[str, str]:
    """
    Translate type annotation from implementation types to wrapper types.

    Args:
        annotation: The type annotation to translate
        wrapped_classes: Mapping of wrapper names to impl qualified names
        impl_module: The implementation module name (e.g., "_my_library")

    Returns:
        Tuple of (wrapper_type_str, impl_type_str) as formatted strings

    Examples:
        _my_library.Bar -> ("Bar", "_my_library.Bar")
        list[_my_library.Bar] -> ("list[Bar]", "list[_my_library.Bar]")
        str -> ("str", "str")  # no translation needed
        typing.Any -> ("typing.Any", "typing.Any")  # no translation
    """
    # Format the annotation to get string representation
    impl_str = _format_type_annotation(annotation)
    wrapper_str = impl_str

    # Replace each wrapped class reference
    for wrapper_name, impl_qualified in wrapped_classes.items():
        # Replace fully qualified name (e.g., "_my_library.Bar" -> "Bar")
        wrapper_str = wrapper_str.replace(impl_qualified, wrapper_name)

    return wrapper_str, impl_str


def _needs_translation(annotation, wrapped_classes: dict[str, str]) -> bool:
    """
    Check if a type annotation contains any wrapped class types that need translation.

    Args:
        annotation: The type annotation to check
        wrapped_classes: Mapping of wrapper names to impl qualified names

    Returns:
        True if the annotation contains at least one wrapped class type
    """
    if annotation == inspect.Signature.empty:
        return False

    impl_str = _format_type_annotation(annotation)

    # Check if any wrapped class appears in the type string
    for impl_qualified in wrapped_classes.values():
        if impl_qualified in impl_str:
            return True

    return False


def _build_unwrap_expr(annotation, wrapped_classes: dict[str, str], var_name: str = "value") -> str:
    """
    Build Python expression to unwrap a value from wrapper type to implementation type.

    This generates annotation-driven unwrapping code that extracts ._impl_instance
    from wrapper objects.

    Args:
        annotation: The type annotation
        wrapped_classes: Mapping of wrapper names to impl qualified names
        var_name: The variable name to unwrap (default: "value")

    Returns:
        Python expression string that unwraps the value

    Examples:
        Bar -> "value._impl_instance"
        list[Bar] -> "[x._impl_instance for x in value]"
        dict[str, Bar] -> "{k: v._impl_instance for k, v in value.items()}"
        Optional[Bar] -> "value._impl_instance if value is not None else None"
        str -> "value"  # no unwrapping needed
    """
    if not _needs_translation(annotation, wrapped_classes):
        return var_name

    # Get the origin and args for generic types
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is None:
        # Direct wrapped class type
        return f"{var_name}._impl_instance"

    elif origin is list:
        if args:
            inner_expr = _build_unwrap_expr(args[0], wrapped_classes, "x")
            return f"[{inner_expr} for x in {var_name}]"
        return var_name

    elif origin is dict:
        if len(args) >= 2:
            value_expr = _build_unwrap_expr(args[1], wrapped_classes, "v")
            if value_expr != "v":
                return f"{{k: {value_expr} for k, v in {var_name}.items()}}"
        return var_name

    elif origin is tuple:
        if args:
            inner_expr = _build_unwrap_expr(args[0], wrapped_classes, "x")
            if inner_expr != "x":
                return f"tuple({inner_expr} for x in {var_name})"
        return var_name

    elif origin is typing.Union:
        # Handle Optional[T] which is Union[T, None]
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            inner_expr = _build_unwrap_expr(non_none_args[0], wrapped_classes, var_name)
            if inner_expr != var_name:
                return f"{inner_expr} if {var_name} is not None else None"
        return var_name

    return var_name


def _build_wrap_expr(annotation, wrapped_classes: dict[str, str], var_name: str = "value") -> str:
    """
    Build Python expression to wrap a value from implementation type to wrapper type.

    This generates annotation-driven wrapping code that calls _wrap_ClassName()
    helper functions (which will be generated separately).

    Args:
        annotation: The type annotation
        wrapped_classes: Mapping of wrapper names to impl qualified names
        var_name: The variable name to wrap (default: "value")

    Returns:
        Python expression string that wraps the value

    Examples:
        Bar -> "_wrap_Bar(value)"
        list[Bar] -> "[_wrap_Bar(x) for x in value]"
        dict[str, Bar] -> "{k: _wrap_Bar(v) for k, v in value.items()}"
        Optional[Bar] -> "_wrap_Bar(value) if value is not None else None"
        str -> "value"  # no wrapping needed
    """
    if not _needs_translation(annotation, wrapped_classes):
        return var_name

    # Get the origin and args for generic types
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is None:
        # Direct wrapped class type - need to find the wrapper name
        impl_str = _format_type_annotation(annotation)
        for wrapper_name, impl_qualified in wrapped_classes.items():
            if impl_str == impl_qualified:
                return f"_wrap_{wrapper_name}({var_name})"
        return var_name

    elif origin is list:
        if args:
            inner_expr = _build_wrap_expr(args[0], wrapped_classes, "x")
            if inner_expr != "x":
                return f"[{inner_expr} for x in {var_name}]"
        return var_name

    elif origin is dict:
        if len(args) >= 2:
            value_expr = _build_wrap_expr(args[1], wrapped_classes, "v")
            if value_expr != "v":
                return f"{{k: {value_expr} for k, v in {var_name}.items()}}"
        return var_name

    elif origin is tuple:
        if args:
            inner_expr = _build_wrap_expr(args[0], wrapped_classes, "x")
            if inner_expr != "x":
                return f"tuple({inner_expr} for x in {var_name})"
        return var_name

    elif origin is typing.Union:
        # Handle Optional[T] which is Union[T, None]
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            inner_expr = _build_wrap_expr(non_none_args[0], wrapped_classes, var_name)
            if inner_expr != var_name:
                return f"{inner_expr} if {var_name} is not None else None"
        return var_name

    return var_name


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
            wrapper_type, impl_type = _translate_type_annotation(
                param.annotation, wrapped_classes, target_module
            )
            param_str = f"{name}: {wrapper_type}"

            # Generate unwrap code if needed
            if _needs_translation(param.annotation, wrapped_classes):
                unwrap_expr = _build_unwrap_expr(param.annotation, wrapped_classes, name)
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
    is_async_generator = _is_async_generator(f, return_annotation)

    # Format return types - translate them
    if _needs_translation(return_annotation, wrapped_classes):
        wrapper_return_type, impl_return_type = _translate_type_annotation(
            return_annotation, wrapped_classes, target_module
        )
        if is_async_generator:
            # Extract yield type from AsyncGenerator
            if hasattr(return_annotation, "__args__") and return_annotation.__args__:
                yield_type = return_annotation.__args__[0]
                wrapper_yield_type, impl_yield_type = _translate_type_annotation(
                    yield_type, wrapped_classes, target_module
                )
                sync_return_str = f" -> typing.Generator[{wrapper_yield_type}, None, None]"
                if len(return_annotation.__args__) > 1:
                    send_type = return_annotation.__args__[1]
                    send_type_str = _format_type_annotation(send_type)
                    async_return_str = f" -> typing.AsyncGenerator[{wrapper_yield_type}, {send_type_str}]"
                else:
                    async_return_str = f" -> typing.AsyncGenerator[{wrapper_yield_type}]"
            else:
                sync_return_str = " -> typing.Generator"
                async_return_str = " -> typing.AsyncGenerator"
        else:
            sync_return_str = f" -> {wrapper_return_type}"
            async_return_str = f" -> {wrapper_return_type}"
    else:
        sync_return_str, async_return_str = _format_return_types(return_annotation, is_async_generator)

    # Generate the wrapper class
    wrapper_class_name = f"_{f.__name__}"

    # Determine if we need to wrap the return value
    needs_return_wrap = _needs_translation(return_annotation, wrapped_classes)

    # Build the aio() method body
    if is_async_generator:
        # For generators, wrap each yielded item
        if needs_return_wrap and hasattr(return_annotation, "__args__"):
            yield_type = return_annotation.__args__[0]
            wrap_expr = _build_wrap_expr(yield_type, wrapped_classes, "item")
            aio_body = f"""        gen = {target_module}.{f.__name__}({call_args_str})
        async for item in self._synchronizer._run_generator_async(gen):
            yield {wrap_expr}"""
        else:
            aio_body = f"""        gen = {target_module}.{f.__name__}({call_args_str})
        async for item in self._synchronizer._run_generator_async(gen):
            yield item"""
    else:
        # For regular async functions
        if needs_return_wrap:
            wrap_expr = _build_wrap_expr(return_annotation, wrapped_classes, "result")
            aio_body = f"""        result = await {target_module}.{f.__name__}({call_args_str})
        return {wrap_expr}"""
        else:
            aio_body = f"""        return await {target_module}.{f.__name__}({call_args_str})"""

    # Build unwrap section for aio() if needed
    aio_unwrap = ""
    if unwrap_code:
        # Adjust indentation for aio method (8 spaces)
        aio_unwrap_lines = [line.replace("    ", "        ", 1) for line in unwrap_stmts]
        aio_unwrap = "\n" + "\n".join(aio_unwrap_lines)

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

    def __call__(self, {param_str}){sync_return_str}:
        return self._sync_wrapper_function({", ".join([p.split(":")[0].split("=")[0].strip() for p in params])})

    async def aio(self, {param_str}){async_return_str}:{aio_unwrap}
{aio_body}
"""

    # Build the sync wrapper function code
    if is_async_generator:
        # For generators, wrap each yielded item
        if needs_return_wrap and hasattr(return_annotation, "__args__"):
            yield_type = return_annotation.__args__[0]
            wrap_expr = _build_wrap_expr(yield_type, wrapped_classes, "item")
            sync_gen_body = f"""    gen = {target_module}.{f.__name__}({call_args_str})
    for item in get_synchronizer('{synchronizer_name}')._run_generator_sync(gen):
        yield {wrap_expr}"""
        else:
            sync_gen_body = f"""    gen = {target_module}.{f.__name__}({call_args_str})
    yield from get_synchronizer('{synchronizer_name}')._run_generator_sync(gen)"""
        sync_function_body = sync_gen_body
    else:
        # For regular async functions
        if needs_return_wrap:
            wrap_expr = _build_wrap_expr(return_annotation, wrapped_classes, "result")
            sync_function_body = f"""    result = get_synchronizer('{synchronizer_name}')._run_function_sync({target_module}.{f.__name__}({call_args_str}))
    return {wrap_expr}"""
        else:
            sync_function_body = f"""    return get_synchronizer('{synchronizer_name}')._run_function_sync({target_module}.{f.__name__}({call_args_str}))"""

    # Add unwrap statements to sync function if needed
    if unwrap_code:
        sync_function_body = f"{unwrap_code}\n{sync_function_body}"

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
            wrapper_type, impl_type = _translate_type_annotation(
                param.annotation, wrapped_classes, target_module
            )
            param_str = f"{name}: {wrapper_type}"

            # Generate unwrap code if needed
            if _needs_translation(param.annotation, wrapped_classes):
                unwrap_expr = _build_unwrap_expr(param.annotation, wrapped_classes, name)
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
    is_async_generator = _is_async_generator(method, return_annotation)

    # Format return types - translate them
    if _needs_translation(return_annotation, wrapped_classes):
        wrapper_return_type, impl_return_type = _translate_type_annotation(
            return_annotation, wrapped_classes, target_module
        )
        if is_async_generator:
            # Extract yield type from AsyncGenerator
            if hasattr(return_annotation, "__args__") and return_annotation.__args__:
                yield_type = return_annotation.__args__[0]
                wrapper_yield_type, impl_yield_type = _translate_type_annotation(
                    yield_type, wrapped_classes, target_module
                )
                sync_return_str = f" -> typing.Generator[{wrapper_yield_type}, None, None]"
                if len(return_annotation.__args__) > 1:
                    send_type = return_annotation.__args__[1]
                    send_type_str = _format_type_annotation(send_type)
                    async_return_str = f" -> typing.AsyncGenerator[{wrapper_yield_type}, {send_type_str}]"
                else:
                    async_return_str = f" -> typing.AsyncGenerator[{wrapper_yield_type}]"
            else:
                sync_return_str = " -> typing.Generator"
                async_return_str = " -> typing.AsyncGenerator"
        else:
            sync_return_str = f" -> {wrapper_return_type}"
            async_return_str = f" -> {wrapper_return_type}"
    else:
        sync_return_str, async_return_str = _format_return_types(return_annotation, is_async_generator)

    # Generate the method wrapper class code
    wrapper_class_name = f"{class_name}_{method_name}"

    # Determine if we need to wrap the return value
    needs_return_wrap = _needs_translation(return_annotation, wrapped_classes)

    # Build the impl call arguments (with unwrapped values)
    impl_call_args = f"self._impl_instance{', ' + call_args_str if call_args_str else ''}"

    # Build the aio() method body
    if is_async_generator:
        # For generators, wrap each yielded item
        if needs_return_wrap and hasattr(return_annotation, "__args__"):
            yield_type = return_annotation.__args__[0]
            wrap_expr = _build_wrap_expr(yield_type, wrapped_classes, "item")
            aio_body = f"""        gen = {target_module}.{class_name}.{method_name}({impl_call_args})
        async for item in self._synchronizer._run_generator_async(gen):
            yield {wrap_expr}"""
        else:
            aio_body = f"""        gen = {target_module}.{class_name}.{method_name}({impl_call_args})
        async for item in self._synchronizer._run_generator_async(gen):
            yield item"""
    else:
        # For regular async methods
        if needs_return_wrap:
            wrap_expr = _build_wrap_expr(return_annotation, wrapped_classes, "result")
            aio_body = f"""        result = await {target_module}.{class_name}.{method_name}({impl_call_args})
        return {wrap_expr}"""
        else:
            aio_body = f"""        return await {target_module}.{class_name}.{method_name}({impl_call_args})"""

    # Build unwrap section for aio() if needed
    aio_unwrap = ""
    if unwrap_code:
        # Adjust indentation for aio method (8 spaces)
        aio_unwrap_lines = [line.replace("        ", "        ", 1) for line in unwrap_stmts]
        aio_unwrap = "\n" + "\n".join(aio_unwrap_lines)

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

    def __call__(self, {param_str}){sync_return_str}:
        return self._unbound_sync_wrapper_method(self._wrapper_instance, {call_params})

    async def aio(self, {param_str}){async_return_str}:{aio_unwrap}
{aio_body}
"""

    # Build the sync wrapper method code
    if is_async_generator:
        # For generators, wrap each yielded item
        if needs_return_wrap and hasattr(return_annotation, "__args__"):
            yield_type = return_annotation.__args__[0]
            wrap_expr = _build_wrap_expr(yield_type, wrapped_classes, "item")
            sync_method_body = f"""        gen = {target_module}.{class_name}.{method_name}({impl_call_args})
        for item in self._synchronizer._run_generator_sync(gen):
            yield {wrap_expr}"""
        else:
            sync_method_body = f"""        gen = {target_module}.{class_name}.{method_name}({impl_call_args})
        yield from self._synchronizer._run_generator_sync(gen)"""
    else:
        # For regular async methods
        if needs_return_wrap:
            wrap_expr = _build_wrap_expr(return_annotation, wrapped_classes, "result")
            sync_method_body = f"""        result = self._synchronizer._run_function_sync({target_module}.{class_name}.{method_name}({impl_call_args}))
        return {wrap_expr}"""
        else:
            sync_method_body = f"""        return self._synchronizer._run_function_sync({target_module}.{class_name}.{method_name}({impl_call_args}))"""

    # Add unwrap statements to sync method if needed
    if unwrap_code:
        sync_method_body = f"{unwrap_code}\n{sync_method_body}"

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
                attr_type = _format_type_annotation(annotation)
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
        init_signature, _, init_call_args_list = _parse_parameters(sig, skip_self=True)
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
    # Determine the implementation module name from the first item's actual __module__
    impl_module = None
    for o, (target_module, target_name) in wrapped_items.items():
        impl_module = o.__module__
        break

    if impl_module is None:
        return ""

    # Extract wrapped classes mapping for type translation
    wrapped_classes = _get_wrapped_classes(wrapped_items)

    # Generate header with imports
    header = f"""import typing

import {impl_module}

from synchronicity2.descriptor import wrapped_function, wrapped_method
from synchronicity2.synchronizer import get_synchronizer

NoneType = None
"""

    compiled_code = [header]

    # Generate wrapper helper functions if there are wrapped classes
    if wrapped_classes:
        wrapper_helpers = _generate_wrapper_helpers(wrapped_classes, impl_module)
        compiled_code.append(wrapper_helpers)
        compiled_code.append("")  # Add blank line after helpers

    for o, (target_module, target_name) in wrapped_items.items():
        print(target_module, target_name, o, file=sys.stderr)
        if isinstance(o, types.FunctionType):
            code = compile_function(o, impl_module, synchronizer_name, wrapped_classes)
            compiled_code.append(code)
            compiled_code.append("")  # Add blank line after function
        elif isinstance(o, type):
            code = compile_class(o, impl_module, synchronizer_name, wrapped_classes)
            compiled_code.append(code)

    return "\n".join(compiled_code)
