"""Parse implementation modules into intermediate representation (no code emission)."""

from __future__ import annotations

import collections.abc
import inspect
import sys
import types
import typing

from synchronicity.module import Module

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
)
from .signature_utils import is_async_generator
from .sync_registry import SyncRegistry
from .transformer_ir import (
    AsyncGeneratorTypeIR,
    AsyncIteratorTypeIR,
    AwaitableTypeIR,
    CoroutineTypeIR,
    TypeTransformerIR,
)
from .transformer_materialize import annotation_to_transformer_ir
from .typevar_codegen import typevar_specs_from_collected


def _check_annotation_for_cross_refs(
    annotation,
    current_module: str,
    sync: SyncRegistry,
    cross_module_refs: dict,
) -> None:
    if isinstance(annotation, type):
        loc = sync.lookup_wrapper(annotation)
        if loc is not None:
            target_module, wrapper_name = loc
            if target_module != current_module:
                if target_module not in cross_module_refs:
                    cross_module_refs[target_module] = set()
                cross_module_refs[target_module].add(wrapper_name)

    args = typing.get_args(annotation)
    if args:
        for arg in args:
            _check_annotation_for_cross_refs(arg, current_module, sync, cross_module_refs)


def cross_module_imports_for_module(
    module_name: str,
    module_items: dict,
    synchronized_types: dict[type, tuple[str, str]],
) -> dict[str, set[str]]:
    sync = SyncRegistry.from_type_map(synchronized_types)
    cross_module_refs: dict[str, set[str]] = {}

    for obj in module_items.keys():
        if isinstance(obj, types.FunctionType):
            annotations = _safe_get_annotations(obj)
            for annotation in annotations.values():
                _check_annotation_for_cross_refs(annotation, module_name, sync, cross_module_refs)
        elif isinstance(obj, type):
            for method_name, method in inspect.getmembers(obj, predicate=inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                annotations = _safe_get_annotations(method)
                for annotation in annotations.values():
                    _check_annotation_for_cross_refs(annotation, module_name, sync, cross_module_refs)

    return cross_module_refs


def build_module_compilation_ir(
    module: Module,
    synchronized_types: dict[type, tuple[str, str]],
) -> ModuleCompilationIR:
    """Step 1–2 for a single output module: layout, cross-refs, and collected type variables."""
    impl_modules = {o.__module__ for o in module.module_items().keys()}
    cross = cross_module_imports_for_module(module.target_module, module.module_items(), synchronized_types)

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

    typevar_specs = typevar_specs_from_collected(
        module_typevars,
        synchronized_types,
        module.target_module,
        impl_modules=frozenset(impl_modules),
    )
    cross_frozen = {k: frozenset(v) for k, v in cross.items()}

    impl_mods = frozenset(impl_modules)
    class_wrappers = tuple(
        parse_class_wrapper_ir(c, module.target_module, synchronized_types, impl_modules=impl_mods) for c in classes
    )
    module_functions_ir_list: list[ModuleLevelFunctionIR] = []
    for f in functions:
        g = sys.modules[f.__module__].__dict__ if f.__module__ in sys.modules else None
        module_functions_ir_list.append(
            parse_module_level_function_ir(
                f, module.target_module, synchronized_types, globals_dict=g, impl_modules=impl_mods
            )
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


def _normalize_return_transformer_ir(
    return_ir: TypeTransformerIR,
    *,
    is_async_gen: bool,
) -> TypeTransformerIR:
    if is_async_gen and isinstance(return_ir, AsyncIteratorTypeIR):
        return AsyncGeneratorTypeIR(yield_item=return_ir.item, send_type_str=None)
    return return_ir


def parse_module_level_function_ir(
    f: types.FunctionType,
    target_module: str,
    synchronized_types: dict[type, tuple[str, str]],
    *,
    globals_dict: dict[str, typing.Any] | None = None,
    runtime_package: str = "synchronicity",
    impl_modules: frozenset[str] | None = None,
) -> ModuleLevelFunctionIR:
    _ = runtime_package  # reserved for parity with API; IR does not embed runtime package on nodes
    sync = SyncRegistry.from_type_map(synchronized_types)
    if impl_modules is None:
        impl_modules = frozenset({f.__module__})
    annotations = _safe_get_annotations(f, globals_dict)
    sig = inspect.signature(f)
    return_annotation = annotations.get("return", sig.return_annotation)
    if is_async_generator(f, return_annotation) and return_annotation == inspect.Signature.empty:
        return_annotation = collections.abc.AsyncGenerator[typing.Any, None]
    return_annotation = _normalize_async_annotation(f, return_annotation)

    return_ir = annotation_to_transformer_ir(
        return_annotation,
        sync,
        owner_impl_type=None,
        impl_modules=impl_modules,
    )

    parameters = parse_parameters_to_ir(
        sig,
        annotations,
        sync,
        skip_first_param=False,
        impl_modules=impl_modules,
    )

    is_async_gen = is_async_generator(f, return_annotation)
    return_ir = _normalize_return_transformer_ir(return_ir, is_async_gen=is_async_gen)

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
    sync: SyncRegistry,
    impl_class: type,
    *,
    owner_has_type_parameters: bool = False,
    method_type: MethodBindingKind = MethodBindingKind.INSTANCE,
    globals_dict: dict[str, typing.Any] | None = None,
    generic_typevars: dict[str, typing.TypeVar | typing.ParamSpec] | None = None,
    impl_modules: frozenset[str] | None = None,
) -> MethodWrapperIR:
    generic_typevar_names = frozenset(generic_typevars.keys()) if generic_typevars else None
    if impl_modules is None:
        impl_modules = frozenset({impl_class.__module__})
    annotations = _safe_get_annotations(method, globals_dict)
    sig = inspect.signature(method)
    return_annotation = annotations.get("return", sig.return_annotation)
    if is_async_generator(method, return_annotation) and return_annotation == inspect.Signature.empty:
        return_annotation = collections.abc.AsyncGenerator[typing.Any, None]
    return_annotation = _normalize_async_annotation(method, return_annotation)

    return_ir = annotation_to_transformer_ir(
        return_annotation,
        sync,
        owner_impl_type=impl_class,
        owner_has_type_parameters=owner_has_type_parameters,
        impl_modules=impl_modules,
        generic_typevar_names=generic_typevar_names,
    )

    skip_first_param = method_type in (MethodBindingKind.INSTANCE, MethodBindingKind.CLASSMETHOD)

    parameters = parse_parameters_to_ir(
        sig,
        annotations,
        sync,
        skip_first_param=skip_first_param,
        owner_impl_type=impl_class,
        owner_has_type_parameters=owner_has_type_parameters,
        impl_modules=impl_modules,
        generic_typevar_names=generic_typevar_names,
    )

    is_async_gen = is_async_generator(method, return_annotation)
    return_ir = _normalize_return_transformer_ir(return_ir, is_async_gen=is_async_gen)

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
    synchronized_types: dict[type, tuple[str, str]],
    *,
    globals_dict: dict[str, typing.Any] | None = None,
    runtime_package: str = "synchronicity",
    impl_modules: frozenset[str] | None = None,
) -> ClassWrapperIR:
    """Collect :class:`ClassWrapperIR` from a live implementation class (parse-time only)."""
    if impl_modules is None:
        impl_modules = frozenset({cls.__module__})
    sync_base = SyncRegistry.from_type_map(synchronized_types)
    sync_self = sync_base.with_impl_class(cls, target_module, cls.__name__)

    wrapped_bases: list[ImplQualifiedRef] = []
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
            loc = sync_base.lookup_wrapper(base)
            if loc is not None:
                wrapped_bases.append(ImplQualifiedRef(base.__module__, base.__qualname__))

    methods: list[tuple[str, types.FunctionType, MethodBindingKind]] = []
    classmethod_staticmethod_names: set[str] = set()
    for name, attr in cls.__dict__.items():
        if name.startswith("_"):
            continue
        if isinstance(attr, classmethod):
            methods.append((name, attr.__func__, MethodBindingKind.CLASSMETHOD))
            classmethod_staticmethod_names.add(name)
        elif isinstance(attr, staticmethod):
            methods.append((name, attr.__func__, MethodBindingKind.STATICMETHOD))
            classmethod_staticmethod_names.add(name)

    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if not name.startswith("_") and name in cls.__dict__ and name not in classmethod_staticmethod_names:
            methods.append((name, method, MethodBindingKind.INSTANCE))

    has_aiter = "__aiter__" in cls.__dict__
    has_anext = "__anext__" in cls.__dict__
    aiter_method = cls.__dict__.get("__aiter__")
    anext_method = cls.__dict__.get("__anext__")

    attributes: list[tuple[str, TypeTransformerIR | None]] = []
    class_annotations = cls.__annotations__ if hasattr(cls, "__annotations__") else {}
    for name, annotation in class_annotations.items():
        if not name.startswith("_"):
            annotations_resolved = _safe_get_annotations(cls, globals_dict)
            resolved_annotation = annotations_resolved.get(name, annotation)
            annotation_ir = annotation_to_transformer_ir(
                resolved_annotation,
                sync_self,
                owner_impl_type=cls,
                owner_has_type_parameters=bool(generic_typevars),
                impl_modules=impl_modules,
                generic_typevar_names=frozenset(generic_typevars.keys()) if generic_typevars else None,
            )
            attributes.append((name, annotation_ir))

    method_irs: list[MethodWrapperIR] = []
    for method_name, method, method_type in methods:
        method_irs.append(
            parse_method_wrapper_ir(
                method,
                method_name,
                sync_self,
                cls,
                owner_has_type_parameters=bool(generic_typevars),
                method_type=method_type,
                globals_dict=globals_dict,
                generic_typevars=generic_typevars if generic_typevars else None,
                impl_modules=impl_modules,
            )
        )

    combined_methods: list[MethodWrapperIR] = []

    init_method = getattr(cls, "__init__", None)
    if init_method and init_method is not object.__init__:
        combined_methods.append(
            parse_method_wrapper_ir(
                init_method,
                "__init__",
                sync_self,
                cls,
                owner_has_type_parameters=bool(generic_typevars),
                method_type=MethodBindingKind.INSTANCE,
                globals_dict=globals_dict,
                generic_typevars=generic_typevars if generic_typevars else None,
                impl_modules=impl_modules,
            )
        )

    combined_methods.extend(method_irs)

    if has_aiter:
        assert aiter_method is not None
        combined_methods.append(
            parse_method_wrapper_ir(
                aiter_method,
                "__aiter__",
                sync_self,
                cls,
                owner_has_type_parameters=bool(generic_typevars),
                method_type=MethodBindingKind.INSTANCE,
                globals_dict=globals_dict,
                generic_typevars=generic_typevars if generic_typevars else None,
                impl_modules=impl_modules,
            )
        )
    if has_anext:
        assert anext_method is not None
        combined_methods.append(
            parse_method_wrapper_ir(
                anext_method,
                "__anext__",
                sync_self,
                cls,
                owner_has_type_parameters=bool(generic_typevars),
                method_type=MethodBindingKind.INSTANCE,
                globals_dict=globals_dict,
                generic_typevars=generic_typevars if generic_typevars else None,
                impl_modules=impl_modules,
            )
        )

    return ClassWrapperIR(
        impl_ref=ImplQualifiedRef(cls.__module__, cls.__qualname__),
        wrapped_base_impl_refs=tuple(wrapped_bases),
        generic_type_parameters=generic_type_parameters,
        attributes=tuple(attributes),
        methods=tuple(combined_methods),
    )
