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
    IteratorProtocolMethodIR,
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
from .type_transformer import create_transformer
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

    typevar_specs = typevar_specs_from_collected(module_typevars, synchronized_types, module.target_module)
    cross_frozen = {k: frozenset(v) for k, v in cross.items()}

    class_wrappers = tuple(parse_class_wrapper_ir(c, module.target_module, synchronized_types) for c in classes)
    module_functions_ir_list: list[ModuleLevelFunctionIR] = []
    for f in functions:
        g = sys.modules[f.__module__].__dict__ if f.__module__ in sys.modules else None
        module_functions_ir_list.append(
            parse_module_level_function_ir(f, module.target_module, synchronized_types, globals_dict=g)
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
) -> ModuleLevelFunctionIR:
    _ = runtime_package  # reserved for parity with API; IR does not embed runtime package on nodes
    sync = SyncRegistry.from_type_map(synchronized_types)
    origin_module = f.__module__
    annotations = _safe_get_annotations(f, globals_dict)
    sig = inspect.signature(f)
    return_annotation = annotations.get("return", sig.return_annotation)
    return_annotation = _normalize_async_annotation(f, return_annotation)

    return_ir = annotation_to_transformer_ir(return_annotation, sync, owner_impl_type=None)

    parameters = parse_parameters_to_ir(
        sig,
        annotations,
        sync,
        skip_first_param=False,
    )

    is_async_gen = is_async_generator(f, return_annotation)
    return_ir = _normalize_return_transformer_ir(return_ir, is_async_gen=is_async_gen)

    needs_async_wrapper = is_async_gen or isinstance(return_ir, (AwaitableTypeIR, CoroutineTypeIR))

    return ModuleLevelFunctionIR(
        impl_ref=ImplQualifiedRef(f.__module__, f.__qualname__),
        origin_module=origin_module,
        impl_name=f.__name__,
        needs_async_wrapper=needs_async_wrapper,
        is_async_gen=is_async_gen,
        parameters=parameters,
        return_transformer_ir=return_ir,
    )


def parse_method_wrapper_ir(
    method: types.FunctionType,
    method_name: str,
    sync: SyncRegistry,
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
) -> MethodWrapperIR:
    _ = generic_typevars  # retained for API compatibility; not stored on IR
    annotations = _safe_get_annotations(method, globals_dict)
    sig = inspect.signature(method)
    return_annotation = annotations.get("return", sig.return_annotation)
    return_annotation = _normalize_async_annotation(method, return_annotation)

    return_ir = annotation_to_transformer_ir(
        return_annotation,
        sync,
        owner_impl_type=impl_class,
        owner_has_type_parameters=owner_has_type_parameters,
    )

    skip_first_param = method_type in ("instance", "classmethod")

    parameters = parse_parameters_to_ir(
        sig,
        annotations,
        sync,
        skip_first_param=skip_first_param,
        owner_impl_type=impl_class,
        owner_has_type_parameters=owner_has_type_parameters,
    )

    is_async_gen = is_async_generator(method, return_annotation)
    return_ir = _normalize_return_transformer_ir(return_ir, is_async_gen=is_async_gen)

    is_async = is_async_gen or isinstance(return_ir, (AwaitableTypeIR, CoroutineTypeIR))

    return MethodWrapperIR(
        method_name=method_name,
        method_type=method_type,
        origin_module=origin_module,
        class_name=class_name,
        current_target_module=current_target_module,
        owner_impl_ref=ImplQualifiedRef(impl_class.__module__, impl_class.__qualname__),
        owner_has_type_parameters=owner_has_type_parameters,
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
) -> ClassWrapperIR:
    """Collect :class:`ClassWrapperIR` from a live implementation class (parse-time only)."""
    sync_base = SyncRegistry.from_type_map(synchronized_types)
    sync_self = sync_base.with_impl_class(cls, target_module, cls.__name__)
    origin_module = cls.__module__
    current_target_module = target_module

    wrapped_bases: list[str] = []
    generic_base: str | None = None
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
                    generic_base = f"typing.Generic[{', '.join(typevar_names)}]"
        elif base is not object and isinstance(base, type):
            loc = sync_base.lookup_wrapper(base)
            if loc is not None:
                base_target_module, base_wrapper_name = loc
                if base_target_module == current_target_module:
                    wrapped_bases.append(base_wrapper_name)
                else:
                    wrapped_bases.append(f"{base_target_module}.{base_wrapper_name}")

    methods: list[tuple[str, types.FunctionType, str]] = []
    classmethod_staticmethod_names: set[str] = set()
    for name, attr in cls.__dict__.items():
        if name.startswith("_"):
            continue
        if isinstance(attr, classmethod):
            methods.append((name, attr.__func__, "classmethod"))
            classmethod_staticmethod_names.add(name)
        elif isinstance(attr, staticmethod):
            methods.append((name, attr.__func__, "staticmethod"))
            classmethod_staticmethod_names.add(name)

    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if not name.startswith("_") and name in cls.__dict__ and name not in classmethod_staticmethod_names:
            methods.append((name, method, "instance"))

    has_aiter = "__aiter__" in cls.__dict__
    has_anext = "__anext__" in cls.__dict__
    aiter_method = cls.__dict__.get("__aiter__")
    anext_method = cls.__dict__.get("__anext__")

    attributes: list[tuple[str, str]] = []
    class_annotations = cls.__annotations__ if hasattr(cls, "__annotations__") else {}
    for name, annotation in class_annotations.items():
        if not name.startswith("_"):
            annotations_resolved = _safe_get_annotations(cls, globals_dict)
            resolved_annotation = annotations_resolved.get(name, annotation)
            transformer = create_transformer(resolved_annotation, sync_base, runtime_package)
            attr_type = transformer.wrapped_type(sync_base, current_target_module)
            attributes.append((name, attr_type))

    method_irs: list[MethodWrapperIR] = []
    for method_name, method, method_type in methods:
        method_irs.append(
            parse_method_wrapper_ir(
                method,
                method_name,
                sync_self,
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
        )

    iterator_methods: list[IteratorProtocolMethodIR] = []

    def add_iterator_spec(
        impl_method: types.FunctionType,
        impl_method_name: str,
        sync_method_name: str,
        async_method_name: str,
        *,
        stop_iteration_bridge: bool = False,
    ) -> None:
        method_annotations = _safe_get_annotations(impl_method, globals_dict)
        method_sig = inspect.signature(impl_method)
        method_return_annotation = method_annotations.get("return", method_sig.return_annotation)

        if (
            is_async_generator(impl_method, method_return_annotation)
            and method_return_annotation == inspect.Signature.empty
        ):
            method_return_annotation = collections.abc.AsyncGenerator[typing.Any, None]

        method_return_annotation = _normalize_async_annotation(impl_method, method_return_annotation)
        return_ir = annotation_to_transformer_ir(
            method_return_annotation,
            sync_self,
            owner_impl_type=cls,
            owner_has_type_parameters=bool(generic_typevars),
        )
        is_ag = is_async_generator(impl_method, method_return_annotation)
        return_ir = _normalize_return_transformer_ir(return_ir, is_async_gen=is_ag)

        iterator_methods.append(
            IteratorProtocolMethodIR(
                impl_method_name=impl_method_name,
                sync_method_name=sync_method_name,
                async_method_name=async_method_name,
                return_transformer_ir=return_ir,
                use_async_def=impl_method_name == "__anext__",
                stop_iteration_bridge=stop_iteration_bridge,
            )
        )

    if has_aiter:
        add_iterator_spec(aiter_method, "__aiter__", "__iter__", "__aiter__")
    if has_anext:
        add_iterator_spec(anext_method, "__anext__", "__next__", "__anext__", stop_iteration_bridge=True)

    init_method = getattr(cls, "__init__", None)
    if init_method and init_method is not object.__init__:
        sig = inspect.signature(init_method)
        init_annotations = _safe_get_annotations(init_method, globals_dict)
        init_parameters = parse_parameters_to_ir(
            sig,
            init_annotations,
            sync_base,
            skip_first_param=True,
            owner_impl_type=cls,
            owner_has_type_parameters=bool(generic_typevars),
        )
    else:
        init_parameters = ()

    return ClassWrapperIR(
        impl_ref=ImplQualifiedRef(cls.__module__, cls.__qualname__),
        wrapper_class_name=cls.__name__,
        origin_module=origin_module,
        current_target_module=current_target_module,
        wrapped_base_names=tuple(wrapped_bases),
        generic_base=generic_base,
        owner_has_type_parameters=bool(generic_typevars),
        attributes=tuple(attributes),
        init_parameters=init_parameters,
        methods=tuple(method_irs),
        iterator_methods=tuple(iterator_methods),
    )
