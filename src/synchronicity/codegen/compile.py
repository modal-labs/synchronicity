"""Main compilation module for generating wrapper code using TypeTransformers."""

from __future__ import annotations

import inspect
import types
from typing import TYPE_CHECKING

from .signature_utils import is_async_generator
from .type_transformer import GeneratorTransformer, create_transformer

if TYPE_CHECKING:
    from ..synchronizer import Synchronizer


def _parse_parameters_with_transformers(
    sig: inspect.Signature,
    annotations: dict,
    synchronizer: "Synchronizer",
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

    for name, param in sig.parameters.items():
        if skip_self and name == "self":
            continue

        # Get resolved annotation for this parameter
        param_annotation = annotations.get(name, param.annotation)

        # Create transformer for this parameter
        transformer = create_transformer(param_annotation, synchronizer)

        # Build parameter declaration
        if param_annotation != param.empty:
            wrapper_type_str = transformer.wrapped_type(synchronizer, current_target_module)
            param_str = f"{name}: {wrapper_type_str}"

            # Generate unwrap code if needed
            if transformer.needs_translation():
                unwrap_expr = transformer.unwrap_expr(synchronizer, name)
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
    synchronizer: "Synchronizer",
    current_target_module: str,
    indent: str = "    ",
) -> str:
    """
    Build a function call with optional return value wrapping.

    Args:
        call_expr: The function call expression
        return_transformer: TypeTransformer for the return type
        synchronizer: The Synchronizer instance
        current_target_module: Current target module
        indent: Indentation string

    Returns:
        Code string with the call and optional wrapping
    """
    if return_transformer.needs_translation():
        wrap_expr = return_transformer.wrap_expr(synchronizer, current_target_module, "result")
        return f"""{indent}result = {call_expr}
{indent}return {wrap_expr}"""
    else:
        return f"{indent}return {call_expr}"


def _build_generator_with_wrap(
    gen_expr: str,
    return_transformer,
    synchronizer: "Synchronizer",
    current_target_module: str,
    iterator_expr: str,
    indent: str = "    ",
) -> str:
    """
    Build a generator iteration with optional yielded value wrapping.

    Args:
        gen_expr: Expression to create the generator
        return_transformer: GeneratorTransformer for the return type
        synchronizer: The Synchronizer instance
        current_target_module: Current target module
        iterator_expr: How to iterate (e.g., "for item in gen" or "async for item in gen")
        indent: Indentation string

    Returns:
        Code string with generator iteration and optional wrapping
    """
    if isinstance(return_transformer, GeneratorTransformer) and return_transformer.needs_translation():
        # Get wrap expression for each yielded item
        wrap_expr = return_transformer.get_yield_wrap_expr(synchronizer, current_target_module, "item")
        return f"""{indent}gen = {gen_expr}
{indent}{iterator_expr}:
{indent}    yield {wrap_expr}"""

    # No wrapping needed
    if iterator_expr.startswith("async"):
        # Async generators need explicit loop
        return f"""{indent}gen = {gen_expr}
{indent}{iterator_expr}:
{indent}    yield item"""
    else:
        # Sync generators can use yield from (more efficient)
        # Extract the iterable from "for item in <iterable>"
        iterable = iterator_expr.split(" in ", 1)[1]
        return f"""{indent}gen = {gen_expr}
{indent}yield from {iterable}"""


def _format_return_annotation(
    return_transformer,
    synchronizer: "Synchronizer",
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
    if isinstance(return_transformer, GeneratorTransformer):
        # For generators, sync version returns Generator, async version returns AsyncGenerator
        yield_type_str = return_transformer.yield_transformer.wrapped_type(synchronizer, current_target_module)

        if return_transformer.is_async:
            sync_return_type = f"typing.Generator[{yield_type_str}, None, None]"
            # If send_type_str is None, omit it (for AsyncIterator)
            if return_transformer.send_type_str is None:
                async_return_type = f"typing.AsyncGenerator[{yield_type_str}]"
            else:
                async_return_type = f"typing.AsyncGenerator[{yield_type_str}, {return_transformer.send_type_str}]"
        else:
            # Non-async generator (rare but possible)
            sync_return_type = f"typing.Generator[{yield_type_str}, None, None]"
            async_return_type = sync_return_type
    else:
        # Regular function/method
        wrapper_return_type = return_transformer.wrapped_type(synchronizer, current_target_module)
        if not wrapper_return_type:
            return "", ""
        sync_return_type = wrapper_return_type
        async_return_type = wrapper_return_type

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
    synchronizer: Synchronizer,
) -> str:
    """
    Compile a function into a wrapper class that provides both sync and async versions.

    Args:
        f: The function to compile
        synchronizer: The Synchronizer instance

    Returns:
        String containing the generated wrapper class and decorated function code
    """
    synchronizer_name = synchronizer._name
    origin_module = f.__module__

    # Get the target module for this function
    if f not in synchronizer._wrapped:
        raise ValueError(
            f"Function {f.__name__} from module {origin_module} is not in the synchronizer's "
            f"wrapped dict. Only functions registered with the synchronizer can be compiled."
        )
    current_target_module, _ = synchronizer._wrapped[f]

    # Resolve all type annotations
    annotations = inspect.get_annotations(f, eval_str=True)

    # Get function signature
    sig = inspect.signature(f)
    return_annotation = annotations.get("return", sig.return_annotation)

    # Create transformer for return type
    return_transformer = create_transformer(return_annotation, synchronizer)

    # Parse parameters using transformers
    param_str, call_args_str, unwrap_code = _parse_parameters_with_transformers(
        sig, annotations, synchronizer, current_target_module, skip_self=False, unwrap_indent="    "
    )

    # Check if it's an async generator
    is_async_gen = is_async_generator(f, return_annotation)

    # Check if it's an async function
    is_async_func = inspect.iscoroutinefunction(f) or is_async_gen

    # For non-async functions, generate simple wrapper without @wrapped_function decorator
    if not is_async_func:
        # Format return type annotation (only need sync version)
        sync_return_str, _ = _format_return_annotation(return_transformer, synchronizer, current_target_module)

        # Build function body with wrapping
        function_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            synchronizer,
            current_target_module,
            indent="    ",
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
        return_transformer, synchronizer, current_target_module
    )

    # Generate the wrapper class
    wrapper_class_name = f"_{f.__name__}"

    # Build both sync and async bodies
    if is_async_gen:
        # For async generators, wrap each yielded item
        aio_body = _build_generator_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            synchronizer,
            current_target_module,
            "async for item in self._synchronizer._run_generator_async(gen)",
            indent="        ",
        )
        sync_function_body = _build_generator_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            synchronizer,
            current_target_module,
            f"for item in get_synchronizer('{synchronizer_name}')._run_generator_sync(gen)",
            indent="    ",
        )
    elif is_async_func:
        # For regular async functions
        aio_body = _build_call_with_wrap(
            f"await impl_function({call_args_str})",
            return_transformer,
            synchronizer,
            current_target_module,
            indent="        ",
        )
        sync_runner = f"get_synchronizer('{synchronizer_name}')._run_function_sync"
        sync_function_body = _build_call_with_wrap(
            f"{sync_runner}(impl_function({call_args_str}))",
            return_transformer,
            synchronizer,
            current_target_module,
            indent="    ",
        )
    else:
        # For non-async functions (shouldn't reach here)
        aio_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            synchronizer,
            current_target_module,
            indent="        ",
        )
        sync_function_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            synchronizer,
            current_target_module,
            indent="    ",
        )

    # Build unwrap section for aio() if needed
    aio_impl_ref = f"        impl_function = {origin_module}.{f.__name__}"
    aio_unwrap = f"\n{aio_impl_ref}"
    if unwrap_code:
        # Adjust indentation for aio method (8 spaces)
        aio_unwrap_lines = [line.replace("    ", "        ", 1) for line in unwrap_code.split("\n")]
        aio_unwrap += "\n" + "\n".join(aio_unwrap_lines)

    # Simplified wrapper class that inherits from AioWrapper
    # Specify generic parameters for proper type inference
    # Extract parameter types for the generic specification
    param_types = []
    for name, param in sig.parameters.items():
        param_annotation = annotations.get(name, param.annotation)
        if param_annotation != param.empty:
            transformer = create_transformer(param_annotation, synchronizer)
            wrapper_type_str = transformer.wrapped_type(synchronizer, current_target_module)
            param_types.append(wrapper_type_str)
        else:
            param_types.append("typing.Any")

    # Format the return type for the generic specification
    if return_transformer.wrapped_type(synchronizer, current_target_module):
        return_type_for_generic = return_transformer.wrapped_type(synchronizer, current_target_module)
    else:
        return_type_for_generic = "None"

    # Build the generic specification: AioWrapper[[param_types...], return_type]
    if param_types:
        generic_params = f"[[{', '.join(param_types)}], {return_type_for_generic}]"
    else:
        generic_params = f"[[], {return_type_for_generic}]"

    wrapper_class_code = f"""class {wrapper_class_name}(AioWrapper{generic_params}):
    async def aio(self, {param_str}){async_return_str}:{aio_unwrap}
{aio_body}
"""

    # Add impl_function reference and unwrap statements to sync function
    impl_ref = f"    impl_function = {origin_module}.{f.__name__}"
    if unwrap_code:
        sync_function_body = f"{impl_ref}\n{unwrap_code}\n{sync_function_body}"
    else:
        sync_function_body = f"{impl_ref}\n{sync_function_body}"

    # Use the AioWrapper subclass directly as a decorator (no need for @wrapped_function)
    sync_function_code = f"""@{wrapper_class_name}
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

    Args:
        method: The method to wrap
        method_name: The name of the method
        synchronizer: The Synchronizer instance
        origin_module: The module where the original class is defined
        class_name: The name of the class containing the method
        current_target_module: The target module for the wrapper

    Returns:
        Tuple of (wrapper_class_code, sync_method_code)
    """
    # Resolve all type annotations
    annotations = inspect.get_annotations(method, eval_str=True)

    # Get method signature
    sig = inspect.signature(method)
    return_annotation = annotations.get("return", sig.return_annotation)

    # Create transformer for return type
    return_transformer = create_transformer(return_annotation, synchronizer)

    # Parse parameters using transformers (skip 'self' for methods)
    param_str, call_args_str, unwrap_code = _parse_parameters_with_transformers(
        sig, annotations, synchronizer, current_target_module, skip_self=True, unwrap_indent="        "
    )

    # Extract parameter names (skip 'self')
    param_names = [name for name in sig.parameters.keys() if name != "self"]
    param_names_str = ", ".join(param_names)

    # Check if it's an async generator
    is_async_gen = is_async_generator(method, return_annotation)

    # Check if it's async
    is_async = inspect.iscoroutinefunction(method) or is_async_gen

    # If not async at all, return empty strings (no wrapper needed)
    if not is_async:
        return "", ""

    # Format return types
    sync_return_str, async_return_str = _format_return_annotation(
        return_transformer, synchronizer, current_target_module
    )

    # Generate the wrapper class
    wrapper_class_name = f"{class_name}_{method_name}"

    # Build both sync and async bodies
    if is_async_gen:
        # For async generator methods
        aio_body = _build_generator_with_wrap(
            f"impl_method(self._wrapper_instance._impl_instance, {call_args_str})",
            return_transformer,
            synchronizer,
            current_target_module,
            "async for item in gen",
            indent="        ",
        )
        sync_method_body = _build_generator_with_wrap(
            f"impl_method(self._impl_instance, {call_args_str})",
            return_transformer,
            synchronizer,
            current_target_module,
            "for item in self._synchronizer._run_generator_sync(gen)",
            indent="        ",
        )
    else:
        # For regular async methods
        aio_body = _build_call_with_wrap(
            f"await impl_method(self._wrapper_instance._impl_instance, {call_args_str})",
            return_transformer,
            synchronizer,
            current_target_module,
            indent="        ",
        )
        sync_method_body = _build_call_with_wrap(
            f"self._synchronizer._run_function_sync(impl_method(self._impl_instance, {call_args_str}))",
            return_transformer,
            synchronizer,
            current_target_module,
            indent="        ",
        )

    # Build unwrap section for aio() if needed
    aio_impl_ref = f"        impl_method = {origin_module}.{class_name}.{method_name}"
    aio_unwrap = f"\n{aio_impl_ref}"
    if unwrap_code:
        aio_unwrap += "\n" + unwrap_code

    wrapper_class_code = f"""class {wrapper_class_name}:
    def __init__(self, wrapper_instance, unbound_sync_wrapper_method: typing.Callable[..., typing.Any]):
        self._wrapper_instance = wrapper_instance
        self._unbound_sync_wrapper_method = unbound_sync_wrapper_method

    def __call__(self, {param_str}){sync_return_str}:
        return self._unbound_sync_wrapper_method(self._wrapper_instance, {param_names_str})

    async def aio(self, {param_str}){async_return_str}:{aio_unwrap}
{aio_body}
"""

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
    Compile a class into a wrapper class where all methods are wrapped.

    Args:
        cls: The class to compile
        synchronizer: The Synchronizer instance

    Returns:
        String containing the generated wrapper class code
    """
    synchronizer_name = synchronizer._name
    origin_module = cls.__module__

    # Get the target module for this class
    if cls not in synchronizer._wrapped:
        raise ValueError(
            f"Class {cls.__name__} from module {origin_module} is not in the synchronizer's "
            f"wrapped dict. Only classes registered with the synchronizer can be compiled."
        )
    current_target_module, _ = synchronizer._wrapped[cls]

    # Get all methods from the class
    methods = []
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if not name.startswith("_"):
            methods.append((name, method))

    # Get class attributes from annotations
    attributes = []
    class_annotations = inspect.get_annotations(cls, eval_str=True)
    for name, annotation in class_annotations.items():
        if not name.startswith("_"):
            transformer = create_transformer(annotation, synchronizer)
            attr_type = transformer.wrapped_type(synchronizer, current_target_module)
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
        if wrapper_class_code:
            method_wrapper_classes.append(wrapper_class_code)
        method_definitions.append(sync_method_code)

    # Get __init__ signature
    init_method = getattr(cls, "__init__", None)
    if init_method and init_method is not object.__init__:
        sig = inspect.signature(init_method)
        init_annotations = inspect.get_annotations(init_method, eval_str=True)

        # Parse parameters (skip self)
        init_params = []
        init_call_args = []
        for name, param in sig.parameters.items():
            if name == "self":
                continue

            # Build parameter with type annotation if available
            param_annotation = init_annotations.get(name, param.annotation)
            if param_annotation != param.empty:
                transformer = create_transformer(param_annotation, synchronizer)
                type_str = transformer.wrapped_type(synchronizer, current_target_module)
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


def _get_cross_module_imports(
    module_name: str,
    module_items: dict,
    synchronizer: Synchronizer,
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
                _check_annotation_for_cross_refs(annotation, module_name, synchronizer, cross_module_refs)
        elif isinstance(obj, type):
            # Check methods of the class
            for method_name, method in inspect.getmembers(obj, predicate=inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                annotations = inspect.get_annotations(method, eval_str=True)
                for annotation in annotations.values():
                    _check_annotation_for_cross_refs(annotation, module_name, synchronizer, cross_module_refs)

    return cross_module_refs


def _check_annotation_for_cross_refs(
    annotation,
    current_module: str,
    synchronizer: Synchronizer,
    cross_module_refs: dict,
) -> None:
    """Check a type annotation for references to wrapped classes from other modules."""
    # Handle direct class references
    if isinstance(annotation, type) and annotation in synchronizer._wrapped:
        target_module, wrapper_name = synchronizer._wrapped[annotation]
        if target_module != current_module:
            if target_module not in cross_module_refs:
                cross_module_refs[target_module] = set()
            cross_module_refs[target_module].add(wrapper_name)

    # Handle generic types
    import typing

    args = typing.get_args(annotation)
    if args:
        for arg in args:
            _check_annotation_for_cross_refs(arg, current_module, synchronizer, cross_module_refs)


def compile_module(
    module_name: str,
    synchronizer: Synchronizer,
) -> str:
    """
    Compile wrapped items for a single target module.

    Args:
        module_name: The target module name to generate
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

    # Collect unique implementation modules
    impl_modules = set()
    for o, (target_module, target_name) in module_items.items():
        impl_modules.add(o.__module__)

    # Check if there are any wrapped classes (for weakref import)
    has_wrapped_classes = any(isinstance(o, type) for o in module_items.keys())

    # Detect cross-module references
    cross_module_imports = _get_cross_module_imports(module_name, module_items, synchronizer)

    # Generate header with imports
    imports = "\n".join(f"import {mod}" for mod in sorted(impl_modules))

    # Generate cross-module imports
    cross_module_import_strs = []
    for target_module in sorted(cross_module_imports.keys()):
        cross_module_import_strs.append(f"import {target_module}")

    cross_module_imports_str = "\n".join(cross_module_import_strs) if cross_module_import_strs else ""

    header = f"""import typing

{imports}

from synchronicity.descriptor import AioWrapper, wrapped_function, wrapped_method
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
        compiled_code.append("")  # Add blank line

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

    # Group items by target module
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
