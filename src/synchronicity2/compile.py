import collections.abc
import inspect
import sys
import types
import typing


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
            # Format annotation properly - handle generic types
            if hasattr(param.annotation, "__origin__"):
                # This is a generic type like list[str], dict[str, int], etc.
                # Use repr() to get the full generic type signature
                annotation_str = repr(param.annotation)
            elif hasattr(param.annotation, "__module__") and hasattr(param.annotation, "__name__"):
                if param.annotation.__module__ in ("builtins", "__builtin__"):
                    annotation_str = param.annotation.__name__
                else:
                    annotation_str = f"{param.annotation.__module__}.{param.annotation.__name__}"
            else:
                annotation_str = repr(param.annotation)
            param_str += f": {annotation_str}"

        if param.default is not param.empty:
            default_val = repr(param.default)
            param_str += f" = {default_val}"

        params.append(param_str)

    param_str = ", ".join(params)

    # Format return annotation
    if return_annotation != sig.empty:
        if hasattr(return_annotation, "__origin__"):
            # This is a generic type like list[str], dict[str, int], etc.
            # Use repr() to get the full generic type signature
            return_annotation_str = repr(return_annotation)
        elif hasattr(return_annotation, "__module__") and hasattr(return_annotation, "__name__"):
            if return_annotation.__module__ in ("builtins", "__builtin__"):
                return_annotation_str = return_annotation.__name__
            else:
                return_annotation_str = f"{return_annotation.__module__}.{return_annotation.__name__}"
        else:
            return_annotation_str = repr(return_annotation)

        # Handle different return types
        if is_async_generator:
            # For async generators, sync version returns Iterator[T], async version returns AsyncGenerator[T, None]
            if hasattr(return_annotation, "__args__") and return_annotation.__args__:
                # Extract the yielded type from AsyncGenerator[T, Send]
                yield_type = return_annotation.__args__[0]
                if hasattr(yield_type, "__module__") and hasattr(yield_type, "__name__"):
                    if yield_type.__module__ in ("builtins", "__builtin__"):
                        yield_type_str = yield_type.__name__
                    else:
                        yield_type_str = f"{yield_type.__module__}.{yield_type.__name__}"
                else:
                    yield_type_str = repr(yield_type)
                sync_return_annotation = f"typing.Iterator[{yield_type_str}]"

                # For async generators, also extract the send type (usually None) for proper typing
                if len(return_annotation.__args__) > 1:
                    send_type = return_annotation.__args__[1]
                    if hasattr(send_type, "__module__") and hasattr(send_type, "__name__"):
                        if send_type.__module__ in ("builtins", "__builtin__"):
                            send_type_str = send_type.__name__
                        else:
                            send_type_str = f"{send_type.__module__}.{send_type.__name__}"
                    else:
                        send_type_str = repr(send_type)
                    async_return_annotation = f"typing.AsyncGenerator[{yield_type_str}, {send_type_str}]"
                else:
                    async_return_annotation = f"typing.AsyncGenerator[{yield_type_str}]"
            else:
                sync_return_annotation = "typing.Iterator"
                async_return_annotation = "typing.AsyncGenerator"
        elif return_annotation_str.startswith("typing.Awaitable[") and return_annotation_str.endswith("]"):
            # For async functions, remove the Awaitable wrapper for the sync version
            sync_return_annotation = return_annotation_str[17:-1]  # Remove "typing.Awaitable[" and "]"
            async_return_annotation = return_annotation_str
        elif hasattr(return_annotation, "__origin__") and return_annotation.__origin__ is typing.Awaitable:
            # Extract the inner type from Awaitable[T]
            if return_annotation.__args__:
                inner_type = return_annotation.__args__[0]
                if hasattr(inner_type, "__module__") and hasattr(inner_type, "__name__"):
                    if inner_type.__module__ in ("builtins", "__builtin__"):
                        sync_return_annotation = inner_type.__name__
                    else:
                        sync_return_annotation = f"{inner_type.__module__}.{inner_type.__name__}"
                else:
                    sync_return_annotation = repr(inner_type)
            else:
                sync_return_annotation = return_annotation_str
            async_return_annotation = return_annotation_str
        else:
            sync_return_annotation = return_annotation_str
            async_return_annotation = return_annotation_str

        sync_return_str = f" -> {sync_return_annotation}"
        async_return_str = f" -> {async_return_annotation}"
    else:
        sync_return_str = ""
        async_return_str = ""

    # Determine which method to use based on return type
    if is_async_generator:
        method_name = "_run_generator_sync"
        async_method_name = "_run_generator_async"
    else:
        method_name = "_run_function_sync"
        async_method_name = "_run_function_async"

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
        yield from self.synchronizer.{method_name}(gen)"""
        async_body = f"""        gen = self.impl_function({call_args_str})
        async for item in self.synchronizer.{async_method_name}(gen):
            yield item"""
    else:
        sync_body = f"""        coro = self.impl_function({call_args_str})
        raw_result = self.synchronizer.{method_name}(coro)
        return raw_result"""
        async_body = f"""        coro = self.impl_function({call_args_str})
        raw_result = await self.synchronizer.{async_method_name}(coro)
        return raw_result"""

    sync_code = f"""from synchronicity2.synchronizer import get_synchronizer

class {class_name}:
    synchronizer = get_synchronizer('{synchronizer_name}')
    impl_function = {target_module}.{f.__name__}  # reference to original function

    def __call__(self, {param_str}){sync_return_str}:
{sync_body}

    async def aio(self, {param_str}){async_return_str}:
{async_body}

{f.__name__} = {class_name}()"""

    return sync_code


def compile_method_wrapper(
    method: types.FunctionType, method_name: str, synchronizer_name: str, target_module: str, class_name: str
) -> str:
    """
    Compile a method wrapper descriptor that provides both sync and async versions.

    Args:
        method: The method to wrap
        method_name: The name of the method
        synchronizer_name: The name of the synchronizer to use
        target_module: The module where the original class is located
        class_name: The name of the class containing the method

    Returns:
        String containing the generated method wrapper descriptor code
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
            # Format annotation properly - handle generic types
            if hasattr(param.annotation, "__origin__"):
                annotation_str = repr(param.annotation)
            elif hasattr(param.annotation, "__module__") and hasattr(param.annotation, "__name__"):
                if param.annotation.__module__ in ("builtins", "__builtin__"):
                    annotation_str = param.annotation.__name__
                else:
                    annotation_str = f"{param.annotation.__module__}.{param.annotation.__name__}"
            else:
                annotation_str = repr(param.annotation)
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
        if hasattr(return_annotation, "__origin__"):
            return_annotation_str = repr(return_annotation)
        elif hasattr(return_annotation, "__module__") and hasattr(return_annotation, "__name__"):
            if return_annotation.__module__ in ("builtins", "__builtin__"):
                return_annotation_str = return_annotation.__name__
            else:
                return_annotation_str = f"{return_annotation.__module__}.{return_annotation.__name__}"
        else:
            return_annotation_str = repr(return_annotation)

        # Handle different return types
        if is_async_generator:
            if hasattr(return_annotation, "__args__") and return_annotation.__args__:
                yield_type = return_annotation.__args__[0]
                if hasattr(yield_type, "__module__") and hasattr(yield_type, "__name__"):
                    if yield_type.__module__ in ("builtins", "__builtin__"):
                        yield_type_str = yield_type.__name__
                    else:
                        yield_type_str = f"{yield_type.__module__}.{yield_type.__name__}"
                else:
                    yield_type_str = repr(yield_type)
                sync_return_annotation = f"typing.Iterator[{yield_type_str}]"

                if len(return_annotation.__args__) > 1:
                    send_type = return_annotation.__args__[1]
                    if hasattr(send_type, "__module__") and hasattr(send_type, "__name__"):
                        if send_type.__module__ in ("builtins", "__builtin__"):
                            send_type_str = send_type.__name__
                        else:
                            send_type_str = f"{send_type.__module__}.{send_type.__name__}"
                    else:
                        send_type_str = repr(send_type)
                    async_return_annotation = f"typing.AsyncGenerator[{yield_type_str}, {send_type_str}]"
                else:
                    async_return_annotation = f"typing.AsyncGenerator[{yield_type_str}]"
            else:
                sync_return_annotation = "typing.Iterator"
                async_return_annotation = "typing.AsyncGenerator"
        elif return_annotation_str.startswith("typing.Awaitable[") and return_annotation_str.endswith("]"):
            sync_return_annotation = return_annotation_str[17:-1]
            async_return_annotation = return_annotation_str
        elif hasattr(return_annotation, "__origin__") and return_annotation.__origin__ is typing.Awaitable:
            if return_annotation.__args__:
                inner_type = return_annotation.__args__[0]
                if hasattr(inner_type, "__module__") and hasattr(inner_type, "__name__"):
                    if inner_type.__module__ in ("builtins", "__builtin__"):
                        sync_return_annotation = inner_type.__name__
                    else:
                        sync_return_annotation = f"{inner_type.__module__}.{inner_type.__name__}"
                else:
                    sync_return_annotation = repr(inner_type)
            else:
                sync_return_annotation = return_annotation_str
            async_return_annotation = return_annotation_str
        else:
            sync_return_annotation = return_annotation_str
            async_return_annotation = return_annotation_str

        sync_return_str = f" -> {sync_return_annotation}"
        async_return_str = f" -> {async_return_annotation}"
    else:
        if is_async_generator:
            # For async generators without return annotations, use generic types
            sync_return_str = " -> typing.Iterator"
            async_return_str = " -> typing.AsyncGenerator"
        else:
            sync_return_str = ""
            async_return_str = ""

    # Determine which method to use based on return type
    if is_async_generator:
        method_name_sync = "_run_generator_sync"
        method_name_async = "_run_generator_async"
    else:
        method_name_sync = "_run_function_sync"
        method_name_async = "_run_function_async"

    # Generate the method wrapper descriptor code
    wrapper_class_name = f"_{method_name}MethodWrapper"

    # For async generators, we need to yield from the result instead of returning it
    if is_async_generator:
        if call_args_str:
            sync_body = f"""            gen = self.impl_method(self.instance, {call_args_str})
            yield from self.synchronizer.{method_name_sync}(gen)"""
            async_body = f"""            gen = self.impl_method(self.instance, {call_args_str})
            async for item in self.synchronizer.{method_name_async}(gen):
                yield item"""
        else:
            sync_body = f"""            gen = self.impl_method(self.instance)
            yield from self.synchronizer.{method_name_sync}(gen)"""
            async_body = f"""            gen = self.impl_method(self.instance)
            async for item in self.synchronizer.{method_name_async}(gen):
                yield item"""
    else:
        if call_args_str:
            sync_body = f"""            coro = self.impl_method(self.instance, {call_args_str})
            raw_result = self.synchronizer.{method_name_sync}(coro)
            return raw_result"""
            async_body = f"""            coro = self.impl_method(self.instance, {call_args_str})
            raw_result = await self.synchronizer.{method_name_async}(coro)
            return raw_result"""
        else:
            sync_body = f"""            coro = self.impl_method(self.instance)
            raw_result = self.synchronizer.{method_name_sync}(coro)
            return raw_result"""
            async_body = f"""            coro = self.impl_method(self.instance)
            raw_result = await self.synchronizer.{method_name_async}(coro)
            return raw_result"""

    descriptor_code = f"""
class {wrapper_class_name}:
    synchronizer = get_synchronizer('{synchronizer_name}')
    impl_method = {target_module}.{class_name}.{method_name}  # reference to original method

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return self.BoundMethod(instance, self.synchronizer, self.impl_method)

    class BoundMethod:
        def __init__(self, instance, synchronizer, impl_method):
            self.instance = instance
            self.synchronizer = synchronizer
            self.impl_method = impl_method

        def __call__(self, {param_str}){sync_return_str}:
{sync_body}

        async def aio(self, {param_str}){async_return_str}:
{async_body}"""

    return descriptor_code


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

    # Generate method wrapper descriptors
    method_wrappers = []
    method_assignments = []

    for method_name, method in methods:
        wrapper_code = compile_method_wrapper(method, method_name, synchronizer_name, target_module, cls.__name__)
        method_wrappers.append(wrapper_code)
        method_assignments.append(f"    {method_name} = _{method_name}MethodWrapper()")

    # Generate the wrapper class
    wrapper_class_code = f"""
class {cls.__name__}:
    \"\"\"Wrapper class for {target_module}.{cls.__name__} with sync/async method support\"\"\"

    def __init__(self, *args, **kwargs):
        self._original_instance = {target_module}.{cls.__name__}(*args, **kwargs)

    def __getattr__(self, name):
        # Fallback to original instance for non-wrapped attributes
        return getattr(self._original_instance, name)

{chr(10).join(method_assignments)}"""

    # Combine all the code
    all_code = []
    all_code.extend(method_wrappers)
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
    compiled_code = []

    for o, (target_module, target_name) in wrapped_items.items():
        print(target_module, target_name, o, file=sys.stderr)
        if isinstance(o, types.FunctionType):
            code = compile_function(o, target_module, synchronizer_name)
            compiled_code.append(code)
            print(code)
        elif isinstance(o, type):
            code = (
                f"from synchronicity2.synchronizer import get_synchronizer\n"
                f"{compile_class(o, target_module, synchronizer_name)}"
            )
            compiled_code.append(code)
            print(code)

    return "\n\n".join(compiled_code)
