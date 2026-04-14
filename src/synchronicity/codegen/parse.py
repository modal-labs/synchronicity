"""Parse implementation modules into intermediate representation (no code emission)."""

from __future__ import annotations

import collections.abc
import inspect
import sys
import types
import typing

from synchronicity.module import _IMPL_WRAPPER_LOCATION_ATTR, Module

from .compile_utils import (
    _extract_typevars_from_function,
    _normalize_async_annotation,
    _safe_get_annotations,
    parse_parameters_to_ir,
)
from .ir import (
    ClassWrapperIR,
    ImplQualifiedRef,
    MethodBindingKind,
    MethodWrapperIR,
    ModuleCompilationIR,
    ModuleLevelFunctionIR,
    PropertyWrapperIR,
)
from .signature_utils import is_async_generator
from .transformer_ir import (
    AsyncContextManagerTypeIR,
    AsyncIteratorTypeIR,
    AwaitableTypeIR,
    CoroutineTypeIR,
    TypeTransformerIR,
    WrapperRef,
)
from .transformer_materialize import annotation_to_transformer_ir
from .typevar_codegen import typevar_specs_from_collected


def _get_wrapper_location(t: type) -> tuple[str, str] | None:
    return getattr(t, _IMPL_WRAPPER_LOCATION_ATTR, None)


def _check_annotation_for_cross_refs(
    annotation,
    current_module: str,
    cross_module_refs: dict,
) -> None:
    if isinstance(annotation, type):
        loc = _get_wrapper_location(annotation)
        if loc is not None:
            target_module, wrapper_name = loc
            if target_module != current_module:
                if target_module not in cross_module_refs:
                    cross_module_refs[target_module] = set()
                cross_module_refs[target_module].add(wrapper_name)

    args = typing.get_args(annotation)
    if args:
        for arg in args:
            _check_annotation_for_cross_refs(arg, current_module, cross_module_refs)


def _check_impl_type_for_cross_ref(
    impl_type: type,
    current_module: str,
    cross_module_refs: dict[str, set[str]],
) -> None:
    loc = _get_wrapper_location(impl_type)
    if loc is None:
        return
    target_module, wrapper_name = loc
    if target_module != current_module:
        if target_module not in cross_module_refs:
            cross_module_refs[target_module] = set()
        cross_module_refs[target_module].add(wrapper_name)


def cross_module_imports_for_module(
    module_name: str,
    module_items: dict,
) -> dict[str, set[str]]:
    cross_module_refs: dict[str, set[str]] = {}

    for obj in module_items.keys():
        if isinstance(obj, types.FunctionType):
            annotations = _safe_get_annotations(obj)
            for annotation in annotations.values():
                _check_annotation_for_cross_refs(annotation, module_name, cross_module_refs)
        elif isinstance(obj, type):
            for base in getattr(obj, "__bases__", ()):
                _check_impl_type_for_cross_ref(base, module_name, cross_module_refs)
            for method_name, method in inspect.getmembers(obj, predicate=inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                annotations = _safe_get_annotations(method)
                for annotation in annotations.values():
                    _check_annotation_for_cross_refs(annotation, module_name, cross_module_refs)

    return cross_module_refs


def build_module_compilation_ir(
    module: Module,
) -> ModuleCompilationIR:
    """Step 1–2 for a single output module: layout, cross-refs, and collected type variables."""
    impl_modules = {o.__module__ for o in module.module_items().keys()}
    cross = cross_module_imports_for_module(module.target_module, module.module_items())

    classes: list[type] = []
    functions: list[types.FunctionType] = []
    for o in module.module_items().keys():
        if isinstance(o, type):
            classes.append(o)
        elif isinstance(o, types.FunctionType):
            functions.append(o)

    module_typevars: dict[str, typing.TypeVar | typing.ParamSpec] = {}

    for func in functions:
        annotations = _safe_get_annotations(func)
        module_typevars.update(_extract_typevars_from_function(func, annotations))

    for cls in classes:
        bases_to_check = getattr(cls, "__orig_bases__", cls.__bases__)
        for base in bases_to_check:
            origin = typing.get_origin(base)
            if origin is not None and hasattr(origin, "__name__") and origin.__name__ == "Generic":
                args = typing.get_args(base)
                for arg in args:
                    if isinstance(arg, typing.TypeVar) or isinstance(arg, typing.ParamSpec):
                        module_typevars[arg.__name__] = arg

        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not name.startswith("_"):
                annotations = _safe_get_annotations(method)
                module_typevars.update(_extract_typevars_from_function(method, annotations))

    known_impl_types = frozenset(o for o in module.module_items().keys() if isinstance(o, type))
    typevar_specs = typevar_specs_from_collected(
        module_typevars,
        known_impl_types,
        module.target_module,
        impl_modules=frozenset(impl_modules),
    )
    cross_frozen = {k: frozenset(v) for k, v in cross.items()}

    impl_mods = frozenset(impl_modules)
    class_wrappers = tuple(parse_class_wrapper_ir(c, module.target_module, impl_modules=impl_mods) for c in classes)
    module_functions_ir_list: list[ModuleLevelFunctionIR] = []
    for f in functions:
        g = sys.modules[f.__module__].__dict__ if f.__module__ in sys.modules else None
        module_functions_ir_list.append(
            parse_module_level_function_ir(f, module.target_module, globals_dict=g, impl_modules=impl_mods)
        )
    module_functions_ir = tuple(module_functions_ir_list)

    return ModuleCompilationIR(
        target_module=module.target_module,
        synchronizer_name=module.synchronizer_name,
        impl_modules=frozenset(impl_modules),
        cross_module_imports=cross_frozen,
        typevar_specs=typevar_specs,
        class_wrappers=class_wrappers,
        module_functions_ir=module_functions_ir,
    )


def _detect_async_context_manager_wrapper(f, return_annotation) -> typing.Any | None:
    """Detect functions wrapped by ``@asynccontextmanager``.

    Returns the yield type (context manager value type) if detected, ``None`` otherwise.
    """
    if return_annotation == inspect.Signature.empty:
        return None

    origin = typing.get_origin(return_annotation)
    if origin is not collections.abc.AsyncGenerator:
        return None

    if inspect.isasyncgenfunction(f):
        return None  # Actually is a raw async generator

    # Annotation says AsyncGenerator but function isn't one — check for @asynccontextmanager
    wrapped = getattr(f, "__wrapped__", None)
    if wrapped is not None and inspect.isasyncgenfunction(wrapped):
        args = typing.get_args(return_annotation)
        if args:
            return args[0]
        return typing.Any

    return None


def _normalize_return_transformer_ir(
    return_ir: TypeTransformerIR,
    *,
    is_async_gen: bool,
    func_qualname: str = "",
) -> TypeTransformerIR:
    if is_async_gen and isinstance(return_ir, AsyncIteratorTypeIR):
        raise TypeError(
            f"Async generator function {func_qualname!r} is declared as returning AsyncIterator, "
            f"but should use AsyncGenerator. AsyncIterator hides the generator interface "
            f"(.asend(), .athrow(), .aclose()) from callers."
        )
    return return_ir


def parse_module_level_function_ir(
    f: types.FunctionType,
    target_module: str,
    *,
    globals_dict: dict[str, typing.Any] | None = None,
    runtime_package: str = "synchronicity",
    impl_modules: frozenset[str] | None = None,
) -> ModuleLevelFunctionIR:
    _ = runtime_package  # reserved for parity with API; IR does not embed runtime package on nodes
    if impl_modules is None:
        impl_modules = frozenset({f.__module__})
    annotations = _safe_get_annotations(f, globals_dict)
    sig = inspect.signature(f)
    return_annotation = annotations.get("return", sig.return_annotation)

    # Detect @asynccontextmanager-wrapped functions before async gen normalization
    cm_value_type = _detect_async_context_manager_wrapper(f, return_annotation)
    if cm_value_type is not None:
        value_ir = annotation_to_transformer_ir(cm_value_type, owner_impl_type=None, impl_modules=impl_modules)
        return_ir = AsyncContextManagerTypeIR(value=value_ir)
        parameters = parse_parameters_to_ir(sig, annotations, skip_first_param=False, impl_modules=impl_modules)
        return ModuleLevelFunctionIR(
            impl_ref=ImplQualifiedRef(f.__module__, f.__qualname__),
            needs_async_wrapper=False,
            is_async_gen=False,
            parameters=parameters,
            return_transformer_ir=return_ir,
        )

    if is_async_generator(f, return_annotation) and return_annotation == inspect.Signature.empty:
        return_annotation = collections.abc.AsyncGenerator[typing.Any, None]
    return_annotation = _normalize_async_annotation(f, return_annotation)

    return_ir = annotation_to_transformer_ir(
        return_annotation,
        owner_impl_type=None,
        impl_modules=impl_modules,
    )

    parameters = parse_parameters_to_ir(
        sig,
        annotations,
        skip_first_param=False,
        impl_modules=impl_modules,
    )

    is_async_gen = is_async_generator(f, return_annotation)
    return_ir = _normalize_return_transformer_ir(return_ir, is_async_gen=is_async_gen, func_qualname=f.__qualname__)

    needs_async_wrapper = is_async_gen or isinstance(return_ir, (AwaitableTypeIR, CoroutineTypeIR))

    return ModuleLevelFunctionIR(
        impl_ref=ImplQualifiedRef(f.__module__, f.__qualname__),
        needs_async_wrapper=needs_async_wrapper,
        is_async_gen=is_async_gen,
        parameters=parameters,
        return_transformer_ir=return_ir,
    )


def parse_method_wrapper_ir(
    method: types.FunctionType,
    method_name: str,
    impl_class: type,
    *,
    owner_has_type_parameters: bool = False,
    method_type: MethodBindingKind = MethodBindingKind.INSTANCE,
    globals_dict: dict[str, typing.Any] | None = None,
    generic_typevars: dict[str, typing.TypeVar | typing.ParamSpec] | None = None,
    impl_modules: frozenset[str] | None = None,
) -> MethodWrapperIR:
    if impl_modules is None:
        impl_modules = frozenset({impl_class.__module__})
    annotations = _safe_get_annotations(method, globals_dict)
    sig = inspect.signature(method)
    return_annotation = annotations.get("return", sig.return_annotation)

    # Detect @asynccontextmanager-wrapped methods before async gen normalization
    cm_value_type = _detect_async_context_manager_wrapper(method, return_annotation)
    if cm_value_type is not None:
        value_ir = annotation_to_transformer_ir(
            cm_value_type,
            owner_impl_type=impl_class,
            owner_has_type_parameters=owner_has_type_parameters,
            impl_modules=impl_modules,
        )
        return_ir = AsyncContextManagerTypeIR(value=value_ir)
        skip_first_param = method_type in (MethodBindingKind.INSTANCE, MethodBindingKind.CLASSMETHOD)
        parameters = parse_parameters_to_ir(
            sig,
            annotations,
            skip_first_param=skip_first_param,
            owner_impl_type=impl_class,
            owner_has_type_parameters=owner_has_type_parameters,
            impl_modules=impl_modules,
        )
        return MethodWrapperIR(
            method_name=method_name,
            method_type=method_type,
            parameters=parameters,
            is_async_gen=False,
            is_async=False,
            return_transformer_ir=return_ir,
        )

    # Validate __aiter__ isn't typed as a sync generator/iterator
    if method_name == "__aiter__":
        origin = typing.get_origin(return_annotation)
        if origin in (collections.abc.Generator, collections.abc.Iterator) or (
            inspect.isgeneratorfunction(method) and not inspect.isasyncgenfunction(method)
        ):
            raise TypeError(
                f"{impl_class.__module__}.{impl_class.__qualname__}.__aiter__ "
                "has a sync generator/iterator return type "
                f"but must return an async iterable (AsyncIterator, AsyncGenerator, etc.)."
            )

    if is_async_generator(method, return_annotation) and return_annotation == inspect.Signature.empty:
        return_annotation = collections.abc.AsyncGenerator[typing.Any, None]
    return_annotation = _normalize_async_annotation(method, return_annotation)

    return_ir = annotation_to_transformer_ir(
        return_annotation,
        owner_impl_type=impl_class,
        owner_has_type_parameters=owner_has_type_parameters,
        impl_modules=impl_modules,
    )

    skip_first_param = method_type in (MethodBindingKind.INSTANCE, MethodBindingKind.CLASSMETHOD)

    parameters = parse_parameters_to_ir(
        sig,
        annotations,
        skip_first_param=skip_first_param,
        owner_impl_type=impl_class,
        owner_has_type_parameters=owner_has_type_parameters,
        impl_modules=impl_modules,
    )

    is_async_gen = is_async_generator(method, return_annotation)
    return_ir = _normalize_return_transformer_ir(
        return_ir, is_async_gen=is_async_gen, func_qualname=method.__qualname__
    )

    is_async = is_async_gen or isinstance(return_ir, (AwaitableTypeIR, CoroutineTypeIR))

    return MethodWrapperIR(
        method_name=method_name,
        method_type=method_type,
        parameters=parameters,
        is_async_gen=is_async_gen,
        is_async=is_async,
        return_transformer_ir=return_ir,
    )


def parse_class_wrapper_ir(
    cls: type,
    target_module: str,
    *,
    globals_dict: dict[str, typing.Any] | None = None,
    runtime_package: str = "synchronicity",
    impl_modules: frozenset[str] | None = None,
) -> ClassWrapperIR:
    """Collect :class:`ClassWrapperIR` from a live implementation class (parse-time only)."""
    if impl_modules is None:
        impl_modules = frozenset({cls.__module__})

    wrapped_bases: list[tuple[ImplQualifiedRef, WrapperRef]] = []
    generic_type_parameters: tuple[str, ...] | None = None
    generic_typevars: dict[str, typing.TypeVar | typing.ParamSpec] = {}

    bases_to_check = getattr(cls, "__orig_bases__", cls.__bases__)

    for base in bases_to_check:
        origin = typing.get_origin(base)
        if origin is not None and hasattr(origin, "__name__") and origin.__name__ == "Generic":
            args = typing.get_args(base)
            if args:
                for arg in args:
                    if isinstance(arg, typing.TypeVar) or isinstance(arg, typing.ParamSpec):
                        generic_typevars[arg.__name__] = arg

                typevar_names = [arg.__name__ for arg in args if isinstance(arg, (typing.TypeVar, typing.ParamSpec))]
                if typevar_names:
                    generic_type_parameters = tuple(typevar_names)
        elif base is not object and isinstance(base, type):
            loc = _get_wrapper_location(base)
            if loc is not None:
                wrapped_bases.append((ImplQualifiedRef(base.__module__, base.__qualname__), WrapperRef(*loc)))

    # Collect all source methods: __init__, public methods, and async iterator dunders.
    source_methods: list[tuple[str, types.FunctionType, MethodBindingKind]] = []
    classmethod_staticmethod_names: set[str] = set()

    # __init__ (resolved through MRO — subclasses inherit a non-trivial __init__)
    init_method = getattr(cls, "__init__", None)
    if init_method and init_method is not object.__init__:
        source_methods.append(("__init__", init_method, MethodBindingKind.INSTANCE))

    # classmethods, staticmethods, and properties (descriptor unwrapping requires cls.__dict__)
    property_names: set[str] = set()
    property_irs: list[PropertyWrapperIR] = []
    for name, attr in cls.__dict__.items():
        if name.startswith("_"):
            continue
        if isinstance(attr, classmethod):
            source_methods.append((name, attr.__func__, MethodBindingKind.CLASSMETHOD))
            classmethod_staticmethod_names.add(name)
        elif isinstance(attr, staticmethod):
            source_methods.append((name, attr.__func__, MethodBindingKind.STATICMETHOD))
            classmethod_staticmethod_names.add(name)
        elif isinstance(attr, property):
            property_names.add(name)
            fget = attr.fget
            if fget is not None and inspect.iscoroutinefunction(fget):
                raise TypeError(
                    f"Property {cls.__qualname__}.{name} has an async getter. "
                    f"Properties must be synchronous; use an async method instead."
                )
            # Parse getter return type
            return_ir: TypeTransformerIR | None = None
            if fget is not None:
                getter_annotations = _safe_get_annotations(fget, globals_dict)
                return_annotation = getter_annotations.get("return", inspect.Signature.empty)
                if return_annotation != inspect.Signature.empty:
                    return_ir = annotation_to_transformer_ir(
                        return_annotation,
                        owner_impl_type=cls,
                        owner_has_type_parameters=bool(generic_typevars),
                        impl_modules=impl_modules,
                    )
            # Parse setter value type
            has_setter = attr.fset is not None
            setter_value_ir: TypeTransformerIR | None = None
            if has_setter and attr.fset is not None:
                setter_annotations = _safe_get_annotations(attr.fset, globals_dict)
                setter_sig = inspect.signature(attr.fset)
                setter_params = list(setter_sig.parameters.values())
                if len(setter_params) >= 2:
                    value_param = setter_params[1]
                    setter_annotation = setter_annotations.get(value_param.name, inspect.Signature.empty)
                    if setter_annotation != inspect.Signature.empty:
                        setter_value_ir = annotation_to_transformer_ir(
                            setter_annotation,
                            owner_impl_type=cls,
                            owner_has_type_parameters=bool(generic_typevars),
                            impl_modules=impl_modules,
                        )
            property_irs.append(
                PropertyWrapperIR(
                    name=name,
                    return_transformer_ir=return_ir,
                    has_setter=has_setter,
                    setter_value_ir=setter_value_ir,
                )
            )

    # instance methods (only directly defined on cls)
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if (
            not name.startswith("_")
            and name in cls.__dict__
            and name not in classmethod_staticmethod_names
            and name not in property_names
        ):
            source_methods.append((name, method, MethodBindingKind.INSTANCE))

    # async iterator protocol dunders (only directly defined on cls)
    for dunder_name in ("__aiter__", "__anext__"):
        if dunder_name in cls.__dict__:
            source_methods.append((dunder_name, cls.__dict__[dunder_name], MethodBindingKind.INSTANCE))

    # async context manager protocol dunders (only directly defined on cls)
    for dunder_name in ("__aenter__", "__aexit__"):
        if dunder_name in cls.__dict__:
            source_methods.append((dunder_name, cls.__dict__[dunder_name], MethodBindingKind.INSTANCE))

    attributes: list[tuple[str, TypeTransformerIR | None]] = []
    class_annotations = cls.__annotations__ if hasattr(cls, "__annotations__") else {}
    for name, annotation in class_annotations.items():
        if not name.startswith("_"):
            annotations_resolved = _safe_get_annotations(cls, globals_dict)
            resolved_annotation = annotations_resolved.get(name, annotation)
            annotation_ir = annotation_to_transformer_ir(
                resolved_annotation,
                owner_impl_type=cls,
                owner_has_type_parameters=bool(generic_typevars),
                impl_modules=impl_modules,
            )
            attributes.append((name, annotation_ir))

    # Parse all source methods into IR in one pass
    method_irs = tuple(
        parse_method_wrapper_ir(
            method,
            method_name,
            cls,
            owner_has_type_parameters=bool(generic_typevars),
            method_type=method_type,
            globals_dict=globals_dict,
            generic_typevars=generic_typevars if generic_typevars else None,
            impl_modules=impl_modules,
        )
        for method_name, method, method_type in source_methods
    )

    # Read wrapper location from marker attribute
    wrapper_loc = _get_wrapper_location(cls)
    assert wrapper_loc is not None, f"{cls!r} missing {_IMPL_WRAPPER_LOCATION_ATTR}"
    wrapper_ref = WrapperRef(*wrapper_loc)

    return ClassWrapperIR(
        impl_ref=ImplQualifiedRef(cls.__module__, cls.__qualname__),
        wrapper_ref=wrapper_ref,
        wrapped_bases=tuple(wrapped_bases),
        generic_type_parameters=generic_type_parameters,
        attributes=tuple(attributes),
        properties=tuple(property_irs),
        methods=method_irs,
    )
