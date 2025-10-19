import collections.abc
import inspect
import sys
import types


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


def compile_function(f: types.FunctionType, target_module: str, synchronizer_name: str) -> str:
    """
    Compile a function into a wrapper class that provides both sync and async versions.

    Args:
        f: The function to compile
        target_module: The module name where the original function is located
        synchronizer_name: The name of the synchronizer to use

    Returns:
        String containing the generated wrapper class code
    """
    # Get function signature and annotations
    sig = inspect.signature(f)
    return_annotation = sig.return_annotation

    # Check if it's an async generator
    is_async_generator = (
        hasattr(return_annotation, "__origin__") and return_annotation.__origin__ is collections.abc.AsyncGenerator
    )

    # Build the function signature with type annotations
    params = []
    for name, param in sig.parameters.items():
        param_str = name
        if param.annotation != param.empty:
            annotation_str = _format_type_annotation(param.annotation)
            param_str += f": {annotation_str}"

        if param.default is not param.empty:
            default_val = repr(param.default)
            param_str += f" = {default_val}"

        params.append(param_str)

    param_str = ", ".join(params)

    # Format return annotation
    if return_annotation != sig.empty:
        # Handle different return types
        if is_async_generator:
            # For async generators, sync version returns Iterator[T], async version returns AsyncGenerator[T, None]
            if hasattr(return_annotation, "__args__") and return_annotation.__args__:
                # Extract the yielded type from AsyncGenerator[T, Send]
                yield_type = return_annotation.__args__[0]
                yield_type_str = _format_type_annotation(yield_type)
                sync_return_annotation = f"typing.Iterator[{yield_type_str}]"

                # For async generators, also extract the send type (usually None) for proper typing
                if len(return_annotation.__args__) > 1:
                    send_type = return_annotation.__args__[1]
                    send_type_str = _format_type_annotation(send_type)
                    async_return_annotation = f"typing.AsyncGenerator[{yield_type_str}, {send_type_str}]"
                else:
                    async_return_annotation = f"typing.AsyncGenerator[{yield_type_str}]"
            else:
                sync_return_annotation = "typing.Iterator"
                async_return_annotation = "typing.AsyncGenerator"
        else:
            # For regular async functions
            sync_return_annotation = _format_type_annotation(return_annotation)
            async_return_annotation = sync_return_annotation

        sync_return_str = f" -> {sync_return_annotation}"
        async_return_str = f" -> {async_return_annotation}"
    else:
        sync_return_str = ""
        async_return_str = ""

    # Get the function arguments for calling the original function
    call_args = []
    for name, param in sig.parameters.items():
        call_args.append(name)
    call_args_str = ", ".join(call_args)

    # Generate the class-based wrapper code
    class_name = f"_{f.__name__}Wrapper"

    # For async generators, we need to yield from the result instead of returning it
    if is_async_generator:
        sync_body = f"""        gen = self.impl_function({call_args_str})
        yield from self.synchronizer._run_generator_sync(gen)"""
        async_body = f"""        gen = self.impl_function({call_args_str})
        async for item in self.synchronizer._run_generator_async(gen):
            yield item"""
    else:
        sync_body = f"""        coro = self.impl_function({call_args_str})
        raw_result = self.synchronizer._run_function_sync(coro)
        return raw_result"""
        async_body = f"""        coro = self.impl_function({call_args_str})
        raw_result = await self.synchronizer._run_function_async(coro)
        return raw_result"""

    # Format the parameters for function signature
    if param_str:
        call_signature = f"""
        self,
    ){sync_return_str}:"""
        aio_signature = f"""
        self,
    ){async_return_str}:"""
    else:
        call_signature = f"""self,
    ){sync_return_str}:"""
        aio_signature = f"""self,
    ){async_return_str}:"""

    sync_code = f"""class {class_name}:
    synchronizer = get_synchronizer('{synchronizer_name}')
    impl_function = {target_module}.{f.__name__}  # reference to original function

    def __call__({call_signature}
{sync_body}

    async def aio({aio_signature}
{async_body}


{f.__name__} = {class_name}()"""

    return sync_code


def compile_method_wrapper(
    method: types.FunctionType, method_name: str, synchronizer_name: str, target_module: str, class_name: str
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

    Returns:
        Tuple of (wrapper_class_code, sync_method_code)
    """
    # Get method signature and annotations
    sig = inspect.signature(method)
    return_annotation = sig.return_annotation

    # Check if it's an async generator using inspect.isasyncgenfunction
    is_async_generator = inspect.isasyncgenfunction(method)

    # Also check return annotation for additional type information
    if not is_async_generator and return_annotation != sig.empty:
        is_async_generator = (
            hasattr(return_annotation, "__origin__") and return_annotation.__origin__ is collections.abc.AsyncGenerator
        )

    # Build the method signature with type annotations (excluding 'self')
    params = []
    call_args = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue  # Skip 'self' parameter

        param_str = name
        if param.annotation != param.empty:
            annotation_str = _format_type_annotation(param.annotation)
            param_str += f": {annotation_str}"

        if param.default is not param.empty:
            default_val = repr(param.default)
            param_str += f" = {default_val}"

        params.append(param_str)
        call_args.append(name)

    param_str = ", ".join(params)
    call_args_str = ", ".join(call_args)

    # Format return annotation
    if return_annotation != sig.empty:
        # Handle different return types
        if is_async_generator:
            if hasattr(return_annotation, "__args__") and return_annotation.__args__:
                yield_type = return_annotation.__args__[0]
                yield_type_str = _format_type_annotation(yield_type)
                sync_return_annotation = f"typing.Generator[{yield_type_str}, None, None]"

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
    else:
        if is_async_generator:
            sync_return_str = " -> typing.Generator"
            async_return_str = " -> typing.AsyncGenerator"
        else:
            sync_return_str = ""
            async_return_str = ""

    # Generate the method wrapper class code
    wrapper_class_name = f"{class_name}_{method_name}"

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
        # This is what actually gets called when doing {class_name}().{method_name}(...)
        return self._unbound_sync_wrapper_method(self._wrapper_instance, {call_args_str})

    async def aio(self, {param_str}){async_return_str}:
        gen = {target_module}.{class_name}.{method_name}(self._impl_instance{', ' + call_args_str if call_args_str else ''})
        # TODO: two-way generators...
        async for item in self._synchronizer._run_generator_async(gen):
            yield item
"""

    # Build the sync wrapper method code
    if is_async_generator:
        sync_method_body = f"""        gen = {target_module}.{class_name}.{method_name}(self._impl_instance{', ' + call_args_str if call_args_str else ''})
        yield from self._synchronizer._run_generator_sync(gen)"""
    else:
        sync_method_body = f"""        coro = {target_module}.{class_name}.{method_name}(self._impl_instance{', ' + call_args_str if call_args_str else ''})
        return self._synchronizer._run_function_sync(coro)"""

    sync_method_code = f"""    @wrapped_method({target_module}.{class_name}.{method_name}, {wrapper_class_name})  # this adds the .aio variant
    def {method_name}(self, {param_str}){sync_return_str}:
        # This is where language servers will navigate when going to definition for {class_name}().{method_name}
        # For that reason, we put the generated *sync* proxy implementation here with the
        # sync method signature.
        # However, this is *not* the method that gets immediately called when
        # {class_name}().{method_name}() is called - that goes via the descriptor that in turn calls back to this
        # This complicated control flow is done in order to maximize code navigation usability.
        # This sync method implementation should be really short for that reason and just delegate
        # calls to the original instance + input/output translation
{sync_method_body}"""

    return wrapper_class_code, sync_method_code


def compile_class(cls: type, target_module: str, synchronizer_name: str) -> str:
    """
    Compile a class into a wrapper class where all methods are wrapped with sync/async versions.

    Args:
        cls: The class to compile
        target_module: The module name where the original class is located
        synchronizer_name: The name of the synchronizer to use

    Returns:
        String containing the generated wrapper class code
    """
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
            method, method_name, synchronizer_name, target_module, cls.__name__
        )
        method_wrapper_classes.append(wrapper_class_code)
        method_definitions.append(sync_method_code)

    # Get __init__ signature
    init_method = getattr(cls, "__init__", None)
    if init_method and init_method is not object.__init__:
        sig = inspect.signature(init_method)
        init_params = []
        init_call_args = []
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            param_str = name
            if param.annotation != param.empty:
                annotation_str = _format_type_annotation(param.annotation)
                param_str += f": {annotation_str}"
            if param.default is not param.empty:
                param_str += f" = {repr(param.default)}"
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

    # Generate header with imports
    header = f"""import typing

import {impl_module}

from synchronicity2.descriptor import wrapped_method
from synchronicity2.synchronizer import get_synchronizer

NoneType = None
"""

    compiled_code = [header]

    for o, (target_module, target_name) in wrapped_items.items():
        print(target_module, target_name, o, file=sys.stderr)
        if isinstance(o, types.FunctionType):
            code = compile_function(o, impl_module, synchronizer_name)
            compiled_code.append(code)
            compiled_code.append("")  # Add blank line after function
        elif isinstance(o, type):
            code = compile_class(o, impl_module, synchronizer_name)
            compiled_code.append(code)

    return "\n".join(compiled_code)
