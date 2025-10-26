"""Main compilation module for generating wrapper code using TypeTransformers."""

from __future__ import annotations

import inspect
import types
from typing import TYPE_CHECKING

from synchronicity.module import Module

from .signature_utils import is_async_generator
from .type_transformer import create_transformer

if TYPE_CHECKING:
    pass


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

    for name, param in sig.parameters.items():
        if skip_self and name == "self":
            continue

        # Get resolved annotation for this parameter
        param_annotation = annotations.get(name, param.annotation)

        # Create transformer for this parameter
        transformer = create_transformer(param_annotation, synchronized_types)

        # Build parameter declaration
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
) -> str:
    """
    Build a function call with optional return value wrapping.

    This is used for non-generator return types. For nested generators inside
    return values (e.g., tuple[AsyncGenerator, ...]), we always use is_async=True
    so they remain async generators even in sync calling contexts.

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
        wrap_expr = return_transformer.wrap_expr(synchronized_types, current_target_module, "result", is_async=True)
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
) -> str:
    """
    Compile a function into a wrapper class that provides both sync and async versions.

    Args:
        f: The function to compile
        target_module: Target module where this function will be generated
        synchronizer_name: Name of the synchronizer for async operations
        synchronized_types: Dict mapping impl types to (target_module, wrapper_name)

    Returns:
        String containing the generated wrapper class and decorated function code
    """
    origin_module = f.__module__
    current_target_module = target_module

    # Resolve all type annotations
    annotations = inspect.get_annotations(f, eval_str=True)

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

        # Build function body with wrapping
        function_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            synchronized_types,
            synchronizer_name,
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
        return_transformer, synchronized_types, synchronizer_name, current_target_module
    )

    # Generate the wrapper class
    wrapper_class_name = f"_{f.__name__}"

    # Collect inline helper functions needed by return type
    inline_helpers = return_transformer.get_wrapper_helpers(
        synchronized_types, current_target_module, synchronizer_name, indent="    "
    )
    helpers_code = "\n".join(inline_helpers) if inline_helpers else ""

    # Build both sync and async bodies
    if is_async_gen:
        # For async generators, iterate over helper (can't return generators from async functions)
        wrap_expr = return_transformer.wrap_expr(synchronized_types, current_target_module, "gen")
        aio_body = (
            f"        gen = impl_function({call_args_str})\n"
            f"        async for _item in {wrap_expr}:\n"
            f"            yield _item"
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
        )
        sync_runner = f"get_synchronizer('{synchronizer_name}')._run_function_sync"
        sync_function_body = _build_call_with_wrap(
            f"{sync_runner}(impl_function({call_args_str}))",
            return_transformer,
            synchronized_types,
            synchronizer_name,
            current_target_module,
            indent="    ",
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
        )
        sync_function_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            synchronized_types,
            synchronizer_name,
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
    inline_helpers = return_transformer.get_wrapper_helpers(
        synchronized_types, current_target_module, synchronizer_name, indent="    "
    )
    helpers_code = "\n".join(inline_helpers) if inline_helpers else ""

    # Build both sync and async bodies
    if is_async_gen:
        # For async generator methods, iterate over helper (can't return generators from async functions)
        gen_call = f"impl_method(self._wrapper_instance._impl_instance, {call_args_str})"
        wrap_expr = return_transformer.wrap_expr(synchronized_types, current_target_module, "gen")
        aio_body = f"        gen = {gen_call}\n" f"        async for _item in {wrap_expr}:\n" f"            yield _item"

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

    wrapper_class_code = f"""class {wrapper_class_name}:
    def __init__(self, wrapper_instance):
        self._wrapper_instance = wrapper_instance
{helpers_section}
    def __call__(self, {param_str}){sync_return_str}:{sync_unwrap}
{sync_method_body}

    async def aio(self, {param_str}){async_return_str}:{aio_unwrap}
{aio_body}
"""

    # Extract parameter names (excluding 'self') for the call
    param_names = [name for name in sig.parameters.keys() if name != "self"]
    param_call = ", ".join(param_names)

    # Generate dummy method with descriptor that calls through to wrapper
    sync_method_code = f"""    @wrapped_method({wrapper_class_name})
    def {method_name}(self, {param_str}){sync_return_str}:
        # Dummy method for type checkers and IDE navigation
        # Actual implementation is in {wrapper_class_name}.__call__
        return self.{method_name}({param_call})"""

    return wrapper_class_code, sync_method_code


def compile_class(
    cls: type,
    target_module: str,
    synchronizer_name: str,
    synchronized_types: dict[type, tuple[str, str]],
) -> str:
    """
    Compile a class into a wrapper class where all methods are wrapped.

    Args:
        cls: The class to compile
        synchronizer: The Synchronizer instance

    Returns:
        String containing the generated wrapper class code
    """
    origin_module = cls.__module__
    current_target_module = target_module

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
            transformer = create_transformer(annotation, synchronized_types)
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
