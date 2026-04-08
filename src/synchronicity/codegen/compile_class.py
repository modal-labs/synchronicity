"""Class and method wrapper code generation."""

from __future__ import annotations

import inspect
import types
import typing

from .compile_utils import (
    _build_call_with_wrap,
    _format_return_annotation,
    _normalize_async_annotation,
    _parse_parameters_with_transformers,
    _safe_get_annotations,
)
from .emitters.sync_async_wrappers import emit_method_wrapper_pair
from .parse import parse_method_wrapper_ir
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
    ir = parse_method_wrapper_ir(
        method,
        method_name,
        synchronized_types,
        origin_module,
        class_name,
        current_target_module,
        impl_class,
        owner_has_type_parameters=owner_has_type_parameters,
        method_type=method_type,
        globals_dict=globals_dict,
        generic_typevars=generic_typevars,
        runtime_package=runtime_package,
    )
    return emit_method_wrapper_pair(ir, synchronized_types, runtime_package=runtime_package)


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
