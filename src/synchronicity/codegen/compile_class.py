"""Class and method wrapper code generation."""

from __future__ import annotations

import inspect
import types
import typing

from .compile_utils import (
    _build_call_with_wrap,
    _contains_self_type,
    _format_return_annotation,
    _normalize_async_annotation,
    _parse_parameters_with_transformers,
    _safe_get_annotations,
)
from .signature_utils import is_async_generator
from .type_transformer import create_transformer


def compile_method_wrapper(
    method: types.FunctionType,
    method_name: str,
    synchronized_types: dict[type, tuple[str, str]],
    origin_module: str,
    class_name: str,
    current_target_module: str,
    impl_class: type,
    *,
    owner_has_type_parameters: bool = False,
    method_type: str = "instance",
    globals_dict: dict[str, typing.Any] | None = None,
    generic_typevars: dict[str, typing.TypeVar | typing.ParamSpec] | None = None,
    runtime_package: str = "synchronicity",
) -> tuple[str, str]:
    """
    Compile a method wrapper class that provides both sync and async versions.

    Args:
        method: The method to wrap
        method_name: The name of the method
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
    # Resolve all type annotations (with fallback for TYPE_CHECKING imports)
    annotations = _safe_get_annotations(method, globals_dict)

    # Get method signature
    sig = inspect.signature(method)
    return_annotation = annotations.get("return", sig.return_annotation)

    # Normalize async def annotations to Awaitable[T] for uniform handling
    # Note: async generators are NOT wrapped in Awaitable
    return_annotation = _normalize_async_annotation(method, return_annotation)

    # Check if typing.Self is used in any annotation
    uses_self_type = _contains_self_type(return_annotation) or any(
        _contains_self_type(ann) for ann in annotations.values()
    )

    # Create transformer for return type (typing.Self resolves against impl_class when synchronized)
    return_transformer = create_transformer(
        return_annotation,
        synchronized_types,
        runtime_package,
        owner_impl_type=impl_class,
        owner_has_type_parameters=owner_has_type_parameters,
    )

    # Parse parameters using transformers
    # Skip first parameter for instance methods and classmethods (self/cls),
    # but not for staticmethods
    skip_first_param = method_type in ("instance", "classmethod")

    param_str, call_args_str, unwrap_code = _parse_parameters_with_transformers(
        sig,
        annotations,
        synchronized_types,
        current_target_module,
        runtime_package,
        skip_first_param=skip_first_param,
        unwrap_indent="    ",
        owner_impl_type=impl_class,
        owner_has_type_parameters=owner_has_type_parameters,
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

    # Check if it's an async generator
    # Note: After normalization, async generators are NOT wrapped in Awaitable
    is_async_gen = is_async_generator(method, return_annotation)

    # If it's actually a generator method, override the return transformer to use AsyncGeneratorTransformer
    # even if it's annotated as AsyncIterator (since AsyncGenerator is a subtype of AsyncIterator)
    if is_async_gen:
        from .type_transformer import AsyncGeneratorTransformer, AsyncIteratorTransformer

        if isinstance(return_transformer, AsyncIteratorTransformer):
            # Convert AsyncIteratorTransformer to AsyncGeneratorTransformer
            # since the method is actually a generator
            # Pass send_type_str=None (not "None") to omit the send type from the annotation
            return_transformer = AsyncGeneratorTransformer(return_transformer.item_transformer, send_type_str=None)

    # Import here to avoid circular imports
    from .type_transformer import AwaitableTransformer, CoroutineTransformer

    # Determine if this needs async/sync wrappers based on the transformer type
    # After normalization, async def methods have AwaitableTransformer
    is_async = is_async_gen or isinstance(return_transformer, (AwaitableTransformer, CoroutineTransformer))

    # Format return types
    sync_return_str, async_return_str = _format_return_annotation(
        return_transformer, synchronized_types, current_target_module
    )

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
                current_target_module,
                indent="    ",
                is_async=False,
                method_type=method_type,
                method_owner_impl_type=impl_class,
            )
            # Add impl_method reference
            impl_method_line = f"    impl_method = {origin_module}.{class_name}.{method_name}"
            if unwrap_code:
                sync_method_body = impl_method_line + "\n" + unwrap_code + "\n" + sync_method_body
            else:
                sync_method_body = impl_method_line + "\n" + sync_method_body
            aio_body = None  # No async version for sync methods
        elif is_async_gen:
            # For async generator instance methods
            gen_call = call_expr_prefix
            wrap_expr_raw = return_transformer.wrap_expr(synchronized_types, current_target_module, "gen")
            # Replace self with wrapper_instance for async wrapper function
            wrap_expr = wrap_expr_raw.replace("self.", "wrapper_instance.")
            impl_method_line = f"impl_method = {origin_module}.{class_name}.{method_name}"
            unwrap_lines = f"\n{unwrap_code}\n" if unwrap_code else "\n"
            aio_body = (
                f"    {impl_method_line}{unwrap_lines}"
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
            if unwrap_code:
                sync_method_body = (
                    f"{impl_method_line_sync}\n{unwrap_code}\n    gen = {gen_call}\n    yield from {sync_wrap_expr}"
                )
            else:
                sync_method_body = f"{impl_method_line_sync}\n    gen = {gen_call}\n    yield from {sync_wrap_expr}"
        else:
            # For instance methods returning Awaitable[T] (from normalized async def)
            # The _build_call_with_wrap will handle the synchronizer wrapping
            impl_method_line = f"    impl_method = {origin_module}.{class_name}.{method_name}"

            aio_body = _build_call_with_wrap(
                call_expr_prefix,
                return_transformer,
                synchronized_types,
                current_target_module,
                indent="    ",
                is_async=True,
                method_type=method_type,
                method_owner_impl_type=impl_class,
            )
            if unwrap_code:
                aio_body = impl_method_line + "\n" + unwrap_code + "\n" + aio_body
            else:
                aio_body = impl_method_line + "\n" + aio_body

            sync_method_body = _build_call_with_wrap(
                call_expr_prefix,
                return_transformer,
                synchronized_types,
                current_target_module,
                indent="    ",
                is_async=False,
                method_type=method_type,
                method_owner_impl_type=impl_class,
            )
            if unwrap_code:
                sync_method_body = impl_method_line + "\n" + unwrap_code + "\n" + sync_method_body
            else:
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
                current_target_module,
                indent="    ",
                is_async=False,
                method_type=method_type,
                method_owner_impl_type=impl_class,
            )
            if unwrap_code:
                sync_method_body = unwrap_code + "\n" + sync_method_body
            aio_body = None
        elif is_async_gen:
            # Async generator classmethod
            gen_call = call_expr_prefix
            wrap_expr_raw = return_transformer.wrap_expr(synchronized_types, current_target_module, "gen")
            # Replace self with wrapper_class for async wrapper function
            wrap_expr = wrap_expr_raw.replace("self.", "wrapper_class.")
            unwrap_lines = f"{unwrap_code}\n    " if unwrap_code else ""
            aio_body = (
                f"    {unwrap_lines}gen = {gen_call}\n"
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
            if unwrap_code:
                sync_method_body = f"{unwrap_code}\n    gen = {gen_call}\n    yield from {sync_wrap_expr}"
            else:
                sync_method_body = f"    gen = {gen_call}\n    yield from {sync_wrap_expr}"
        else:
            # For classmethods returning Awaitable[T] (from normalized async def)
            # The _build_call_with_wrap will handle the synchronizer wrapping
            aio_body = _build_call_with_wrap(
                call_expr_prefix,
                return_transformer,
                synchronized_types,
                current_target_module,
                indent="    ",
                is_async=True,
                method_type=method_type,
                method_owner_impl_type=impl_class,
            )
            if unwrap_code:
                aio_body = unwrap_code + "\n" + aio_body

            sync_method_body = _build_call_with_wrap(
                call_expr_prefix,
                return_transformer,
                synchronized_types,
                current_target_module,
                indent="    ",
                is_async=False,
                method_type=method_type,
                method_owner_impl_type=impl_class,
            )
            if unwrap_code:
                sync_method_body = unwrap_code + "\n" + sync_method_body
    elif method_type == "staticmethod":
        # For staticmethod wrapper functions
        if not is_async:
            # Sync staticmethod - just call directly
            sync_call_expr = call_expr_prefix
            sync_method_body = _build_call_with_wrap(
                sync_call_expr,
                return_transformer,
                synchronized_types,
                current_target_module,
                indent="    ",
                is_async=False,
                method_type=method_type,
                method_owner_impl_type=impl_class,
            )
            if unwrap_code:
                sync_method_body = unwrap_code + "\n" + sync_method_body
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
            unwrap_lines = f"{unwrap_code}\n    " if unwrap_code else ""
            aio_body = (
                f"    {unwrap_lines}gen = {gen_call}\n"
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
            if unwrap_code:
                sync_method_body = f"{unwrap_code}\n    gen = {gen_call}\n    yield from {sync_wrap_expr}"
            else:
                sync_method_body = f"    gen = {gen_call}\n    yield from {sync_wrap_expr}"
        else:
            # For staticmethods returning Awaitable[T] (from normalized async def)
            # The _build_call_with_wrap will handle the synchronizer wrapping
            aio_body = _build_call_with_wrap(
                call_expr_prefix,
                return_transformer,
                synchronized_types,
                current_target_module,
                indent="    ",
                is_async=True,
                method_type=method_type,
                method_owner_impl_type=impl_class,
            )
            if unwrap_code:
                aio_body = unwrap_code + "\n" + aio_body

            sync_method_body = _build_call_with_wrap(
                call_expr_prefix,
                return_transformer,
                synchronized_types,
                current_target_module,
                indent="    ",
                is_async=False,
                method_type=method_type,
                method_owner_impl_type=impl_class,
            )
            if unwrap_code:
                sync_method_body = unwrap_code + "\n" + sync_method_body

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
            # Remove 4 spaces from start (base indent) and add 8 spaces, preserving relative indentation
            aio_body_indented = "\n".join(
                (
                    "        " + line[4:]
                    if line.strip() and len(line) > 4 and line.startswith("    ")
                    else "        " + line.lstrip()
                    if line.strip()
                    else ""
                )
                for line in aio_body_lines
            )
            aio_wrapper_method = (
                f"    async def {aio_method_name}(self, {param_str}){async_return_str}:\n{aio_body_indented}"
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
            # Remove 4 spaces from start (base indent) and add 8 spaces, preserving relative indentation
            aio_body_indented = "\n".join(
                (
                    "        " + line[4:]
                    if line.strip() and len(line) > 4 and line.startswith("    ")
                    else "        " + line.lstrip()
                    if line.strip()
                    else ""
                )
                for line in aio_body_lines
            )
            # Add @classmethod decorator to the async wrapper
            # No type annotation needed on cls - it's inferred from context
            aio_wrapper_method = (
                f"    @classmethod\n"
                f"    async def {aio_method_name}(cls, {param_str}){async_return_str}:\n"
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
            # Remove 4 spaces from start (base indent) and add 8 spaces, preserving relative indentation
            aio_body_indented = "\n".join(
                (
                    "        " + line[4:]
                    if line.strip() and len(line) > 4 and line.startswith("    ")
                    else "        " + line.lstrip()
                    if line.strip()
                    else ""
                )
                for line in aio_body_lines
            )
            # Add @staticmethod decorator to the async wrapper
            aio_wrapper_method = (
                f"    @staticmethod\n"
                f"    async def {aio_method_name}({param_str}){async_return_str}:\n"
                f"{aio_body_indented}"
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
        # For classmethods, stack @classmethod with @wrapped_classmethod
        # For staticmethods, stack @staticmethod with @wrapped_staticmethod
        if method_type == "classmethod":
            decorator_line = f"@{decorator_func}({aio_method_name})\n    @classmethod"
        elif method_type == "staticmethod":
            decorator_line = f"@{decorator_func}({aio_method_name})\n    @staticmethod"
        else:
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
        # For classmethods, use plain cls (not cls: type["Class"]) since @classmethod handles binding
        if method_type == "classmethod":
            # Remove type annotation from cls parameter
            if param_str:
                plain_param_str = f"cls, {param_str}"
            else:
                plain_param_str = "cls"
            def_line = f"    def {method_name}({plain_param_str}){sync_return_str}:"
        else:
            # Use dummy_param_str for staticmethods
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
    synchronized_types: dict[type, tuple[str, str]],
    *,
    globals_dict: dict[str, typing.Any] | None = None,
    runtime_package: str = "synchronicity",
) -> str:
    """
    Compile a class into a wrapper class where all methods are wrapped.

    Args:
        cls: The class to compile
        target_module: Target module where this class will be generated
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

    # Check for async iterator protocol methods (__aiter__, __anext__)
    has_aiter = "__aiter__" in cls.__dict__
    has_anext = "__anext__" in cls.__dict__
    aiter_method = cls.__dict__.get("__aiter__")
    anext_method = cls.__dict__.get("__anext__")

    # Get only attributes defined in THIS class (not inherited)
    attributes = []
    # Use cls.__annotations__ directly to get only this class's annotations
    class_annotations = cls.__annotations__ if hasattr(cls, "__annotations__") else {}
    for name, annotation in class_annotations.items():
        if not name.startswith("_"):
            # Resolve forward references using inspect (with fallback for TYPE_CHECKING imports)
            annotations_resolved = _safe_get_annotations(cls, globals_dict)
            resolved_annotation = annotations_resolved.get(name, annotation)
            transformer = create_transformer(resolved_annotation, synchronized_types, runtime_package)
            attr_type = transformer.wrapped_type(synchronized_types, current_target_module)
            attributes.append((name, attr_type))

    # Register this class in synchronized_types so Self references work
    # This allows methods returning Self to be properly wrapped
    synchronized_types_with_self = synchronized_types.copy()
    synchronized_types_with_self[cls] = (current_target_module, cls.__name__)

    # Generate method wrapper classes and method code
    # Note: async wrapper methods are now generated inside the class, not as module-level functions
    # Pair async wrappers with their sync methods so they appear together
    method_definitions_with_async = []

    # Collect helpers from all methods
    all_helpers_dict = {}

    for method_name, method, method_type in methods:
        # Get helpers for this method's return type (with fallback for TYPE_CHECKING imports)
        annotations = _safe_get_annotations(method, globals_dict)
        sig = inspect.signature(method)
        return_annotation = annotations.get("return", sig.return_annotation)
        return_transformer = create_transformer(
            return_annotation,
            synchronized_types_with_self,
            runtime_package,
            owner_impl_type=cls,
            owner_has_type_parameters=bool(generic_typevars),
        )
        method_helpers = return_transformer.get_wrapper_helpers(
            synchronized_types_with_self, current_target_module, indent="    "
        )
        # Merge into all_helpers_dict (deduplicates by key)
        all_helpers_dict.update(method_helpers)

        wrapper_functions_code, sync_method_code = compile_method_wrapper(
            method,
            method_name,
            synchronized_types_with_self,  # Use the version with self registered
            origin_module,
            cls.__name__,
            current_target_module,
            cls,
            owner_has_type_parameters=bool(generic_typevars),
            method_type=method_type,
            globals_dict=globals_dict,
            generic_typevars=generic_typevars if generic_typevars else None,
            runtime_package=runtime_package,
        )
        # Combine async wrapper (if any) with sync method, placing async above sync
        if wrapper_functions_code:
            # Async wrapper methods go right above their sync methods
            method_definitions_with_async.append(f"{wrapper_functions_code}\n\n{sync_method_code}")
        else:
            method_definitions_with_async.append(sync_method_code)

    # Generate helpers section for the class
    helpers_code = "\n".join(all_helpers_dict.values()) if all_helpers_dict else ""
    helpers_section = f"\n{helpers_code}\n" if helpers_code else ""

    # Get __init__ signature
    init_method = getattr(cls, "__init__", None)
    if init_method and init_method is not object.__init__:
        sig = inspect.signature(init_method)
        init_annotations = _safe_get_annotations(init_method, globals_dict)

        # Use _parse_parameters_with_transformers to handle unwrapping
        init_signature, init_call, init_unwrap_code = _parse_parameters_with_transformers(
            sig,
            init_annotations,
            synchronized_types,
            current_target_module,
            runtime_package,
            skip_first_param=True,  # Skip 'self'
            unwrap_indent="        ",  # Indent for __init__ body
            owner_impl_type=cls,
            owner_has_type_parameters=bool(generic_typevars),
        )
    else:
        # No explicit __init__ - use empty signature (not *args, **kwargs)
        init_signature = ""
        init_call = ""
        init_unwrap_code = ""

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
    methods_section = "\n\n".join(method_definitions_with_async) if method_definitions_with_async else ""

    # Generate iterator protocol methods if class implements async iterator protocol
    # The ONLY special thing about these is that we generate both sync and async variants
    # as separate methods (__iter__/__aiter__ or __next__/__anext__) instead of FunctionWithAio.
    iterator_methods_section = ""
    if has_aiter or has_anext:
        iterator_methods = []

        # Helper to generate both sync and async variants of an iterator protocol method
        def generate_iterator_method_pair(
            impl_method: types.FunctionType,
            impl_method_name: str,
            sync_method_name: str,
            async_method_name: str,
            add_exception_handling: bool = False,
        ) -> None:
            """Generate sync and async variants of an iterator protocol method."""
            # Get and normalize annotation (same logic as compile_method_wrapper)
            method_annotations = _safe_get_annotations(impl_method, globals_dict)
            method_sig = inspect.signature(impl_method)
            method_return_annotation = method_annotations.get("return", method_sig.return_annotation)

            # Provide default AsyncGenerator annotation for unannotated async generators
            if (
                is_async_generator(impl_method, method_return_annotation)
                and method_return_annotation == inspect.Signature.empty
            ):
                import collections.abc

                method_return_annotation = collections.abc.AsyncGenerator[typing.Any, None]

            # Normalize async def annotations
            method_return_annotation = _normalize_async_annotation(impl_method, method_return_annotation)

            # Create transformer and collect helpers (typing.Self resolves via owner_impl_type)
            method_return_transformer = create_transformer(
                method_return_annotation,
                synchronized_types_with_self,
                runtime_package,
                owner_impl_type=cls,
                owner_has_type_parameters=bool(generic_typevars),
            )
            method_helpers = method_return_transformer.get_wrapper_helpers(
                synchronized_types_with_self, current_target_module, indent="    "
            )
            all_helpers_dict.update(method_helpers)

            # Format return annotations
            method_sync_return_str, method_async_return_str = _format_return_annotation(
                method_return_transformer, synchronized_types_with_self, current_target_module
            )

            # Build call expression
            method_call_expr = f"{origin_module}.{cls.__name__}.{impl_method_name}(self._impl_instance)"

            # Generate sync variant
            sync_indent = "            " if add_exception_handling else "        "
            sync_body = _build_call_with_wrap(
                method_call_expr,
                method_return_transformer,
                synchronized_types_with_self,
                current_target_module,
                indent=sync_indent,
                is_async=False,
                method_type="instance",
                method_owner_impl_type=cls,
            )
            if add_exception_handling:
                sync_method = f"""    def {sync_method_name}(self){method_sync_return_str}:
        try:
{sync_body}
        except StopAsyncIteration:
            raise StopIteration()"""
            else:
                sync_method = f"""    def {sync_method_name}(self){method_sync_return_str}:
{sync_body}"""
            iterator_methods.append(sync_method)

            # Generate async variant
            # Note: For __aiter__, this is a regular method (not async def) that returns an async iterator
            # For __anext__, this is an async def method
            async_body = _build_call_with_wrap(
                method_call_expr,
                method_return_transformer,
                synchronized_types_with_self,
                current_target_module,
                indent="        ",
                is_async=True,
                method_type="instance",
                method_owner_impl_type=cls,
            )
            # __anext__ should be async def, __aiter__ should be regular def
            async_def_keyword = "async def" if impl_method_name == "__anext__" else "def"
            async_method = f"""    {async_def_keyword} {async_method_name}(self){method_async_return_str}:
{async_body}"""
            iterator_methods.append(async_method)

        if has_aiter:
            generate_iterator_method_pair(aiter_method, "__aiter__", "__iter__", "__aiter__")

        if has_anext:
            generate_iterator_method_pair(
                anext_method, "__anext__", "__next__", "__anext__", add_exception_handling=True
            )

        iterator_methods_section = "\n\n".join(iterator_methods)

    # Regenerate helpers section after processing iterator methods (may have added new helpers)
    helpers_code = "\n".join(all_helpers_dict.values()) if all_helpers_dict else ""
    helpers_section = f"\n{helpers_code}\n" if helpers_code else ""

    # Generate _from_impl classmethod (only for root classes without wrapped bases)
    if not wrapped_bases:
        from_impl_method = f"""    @classmethod
    def _from_impl(cls, impl_instance: {origin_module}.{cls.__name__}) -> "{cls.__name__}":
        \"\"\"Create wrapper from implementation instance, preserving identity via cache.\"\"\"
        return _wrapped_from_impl(cls, impl_instance, cls._instance_cache)"""
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

    _instance_cache: weakref.WeakValueDictionary = weakref.WeakValueDictionary()"""
        )
    else:
        class_attrs = (
            f"""    \"\"\"Wrapper class for {origin_module}.{cls.__name__} with sync/async method support\"\"\""""
        )

    # Generate __init__: unwrap wrapper args, call this class's impl ctor (subclasses use the
    # same pattern as roots — impl __init__ runs the real MRO; no wrapper super() chain).
    # Format signature: "self" or "self, param1, param2, ..."
    init_params = f"self, {init_signature}" if init_signature else "self"

    init_method = f"""    def __init__({init_params}):
{init_unwrap_code}
        self._impl_instance = {origin_module}.{cls.__name__}({init_call})
        type(self)._instance_cache[id(self._impl_instance)] = self"""

    # Build sections list, only including non-empty sections
    sections = [init_method]
    if from_impl_method:
        sections.append(from_impl_method)
    if properties_section:
        sections.append(properties_section)
    if iterator_methods_section:
        sections.append(iterator_methods_section)
    if methods_section:
        sections.append(methods_section)

    sections_combined = "\n\n".join(sections)

    wrapper_class_code = f"""{class_declaration}
{class_attrs}{helpers_section}

{sections_combined}"""

    # Combine all the code
    # Note: async wrapper methods are now inside the class, so no module-level wrapper functions
    all_code = []
    all_code.append(wrapper_class_code)

    return "\n".join(all_code)


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
