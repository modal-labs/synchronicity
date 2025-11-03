"""Main compilation module for generating wrapper code.

This module coordinates the compilation of entire modules by:
- Detecting cross-module imports
- Compiling individual classes and functions
- Assembling complete module files

The actual code generation for functions, classes, and methods is handled by
specialized modules:
- compile_function: Function wrapper generation
- compile_class: Class and method wrapper generation
- compile_utils: Shared utility functions
"""

from __future__ import annotations

import inspect
import sys
import types
import typing

from synchronicity.module import Module

from .compile_class import compile_class
from .compile_function import compile_function
from .compile_utils import _extract_typevars_from_function, _safe_get_annotations


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
            annotations = _safe_get_annotations(obj)
            for annotation in annotations.values():
                _check_annotation_for_cross_refs(annotation, module_name, synchronized_types, cross_module_refs)
        elif isinstance(obj, type):
            # Check methods of the class
            for method_name, method in inspect.getmembers(obj, predicate=inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                annotations = _safe_get_annotations(method)
                for annotation in annotations.values():
                    _check_annotation_for_cross_refs(annotation, module_name, synchronized_types, cross_module_refs)

    return cross_module_refs


def _contains_self_type(annotation) -> bool:
    """Check if a type annotation contains typing.Self.

    Args:
        annotation: Type annotation to check

    Returns:
        True if typing.Self is found anywhere in the annotation
    """
    # Check for typing.Self directly
    if annotation is typing.Self:
        return True

    # Check for generic types with typing.Self as an argument
    origin = typing.get_origin(annotation)
    if origin is not None:
        args = typing.get_args(annotation)
        for arg in args:
            if _contains_self_type(arg):
                return True

    return False


def _translate_typevar_bound(
    bound: type | str, synchronized_types: dict[type, tuple[str, str]], target_module: str
) -> str:
    """Translate a TypeVar bound to the wrapper type if it's a wrapped class.

    Args:
        bound: The bound value (can be a type, string, ForwardRef, or None)
        synchronized_types: Dict mapping implementation types to (target_module, wrapper_name)
        target_module: Current target module for local vs cross-module refs

    Returns:
        String representation of the bound for code generation
    """
    # Handle ForwardRef objects (from string annotations)
    if hasattr(bound, "__forward_arg__"):
        # Extract the string from the ForwardRef
        forward_str = bound.__forward_arg__  # type: ignore
        # Try to find if this string matches any wrapped class name
        for impl_type, (wrapper_target_module, wrapper_name) in synchronized_types.items():
            if impl_type.__name__ == forward_str:
                # Translate to wrapper name, always use string for forward compatibility
                if wrapper_target_module == target_module:
                    return f'"{wrapper_name}"'
                else:
                    return f'"{wrapper_target_module}.{wrapper_name}"'
        # Not a wrapped class, return as-is
        return f'"{forward_str}"'

    # Handle string forward references
    if isinstance(bound, str):
        # Try to find if this string matches any wrapped class name
        for impl_type, (wrapper_target_module, wrapper_name) in synchronized_types.items():
            if impl_type.__name__ == bound:
                # Translate to wrapper name
                if wrapper_target_module == target_module:
                    return wrapper_name
                else:
                    return f"{wrapper_target_module}.{wrapper_name}"
        # Not a wrapped class, return as-is
        return f'"{bound}"'

    # Handle direct type references
    if isinstance(bound, type):
        if bound in synchronized_types:
            # For wrapped classes, always use string forward reference
            # since the class may not be defined yet when TypeVar is declared
            wrapper_target_module, wrapper_name = synchronized_types[bound]
            if wrapper_target_module == target_module:
                return f'"{wrapper_name}"'
            else:
                return f'"{wrapper_target_module}.{wrapper_name}"'
        else:
            # Not a wrapped class, use the actual type name
            if bound.__module__ == "builtins":
                return bound.__name__
            else:
                return f"{bound.__module__}.{bound.__name__}"

    # Fallback: just repr it
    return repr(bound)


def _generate_typevar_definitions(
    typevars: dict[str, typing.TypeVar | typing.ParamSpec],
    synchronized_types: dict[type, tuple[str, str]],
    target_module: str,
) -> list[str]:
    """Generate Python code to recreate TypeVar and ParamSpec definitions.

    Args:
        typevars: Dict mapping typevar name to typevar instance
        synchronized_types: Dict mapping implementation types to (target_module, wrapper_name)
        target_module: Current target module for translating bounds

    Returns:
        List of definition strings like 'T = typing.TypeVar("T", bound=SomeClass)'
    """
    definitions = []

    for name, typevar in typevars.items():
        if isinstance(typevar, typing.ParamSpec):
            # ParamSpec is simpler - just name
            definitions.append(f'{name} = typing.ParamSpec("{name}")')
        elif isinstance(typevar, typing.TypeVar):
            # TypeVar can have bounds, constraints, and variance
            args = [f'"{name}"']

            # Handle constraints (e.g., TypeVar('T', int, str))
            if hasattr(typevar, "__constraints__") and typevar.__constraints__:
                for constraint in typevar.__constraints__:
                    if isinstance(constraint, type):
                        if constraint in synchronized_types:
                            wrapper_target_module, wrapper_name = synchronized_types[constraint]
                            if wrapper_target_module == target_module:
                                args.append(wrapper_name)
                            else:
                                args.append(f"{wrapper_target_module}.{wrapper_name}")
                        else:
                            constraint_name = (
                                f"{constraint.__module__}.{constraint.__name__}"
                                if constraint.__module__ != "builtins"
                                else constraint.__name__
                            )
                            args.append(constraint_name)
                    else:
                        args.append(repr(constraint))

            # Handle bound (e.g., TypeVar('T', bound=SomeClass))
            if hasattr(typevar, "__bound__") and typevar.__bound__ is not None:
                bound_str = _translate_typevar_bound(typevar.__bound__, synchronized_types, target_module)
                args.append(f"bound={bound_str}")

            # Handle covariant/contravariant
            if hasattr(typevar, "__covariant__") and typevar.__covariant__:
                args.append("covariant=True")
            if hasattr(typevar, "__contravariant__") and typevar.__contravariant__:
                args.append("contravariant=True")

            definitions.append(f"{name} = typing.TypeVar({', '.join(args)})")

    return definitions


def compile_module(
    module: Module,
    synchronized_types: dict[type, tuple[str, str]],
    synchronizer_name: str,
) -> str:
    """
    Compile wrapped items for a single target module.

    Args:
        module: The Module instance with registered items
        synchronized_types: Dict mapping all implementation types to (target_module, wrapper_name)
        synchronizer_name: Name of the synchronizer

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

from synchronicity.descriptor import (
    wrapped_classmethod,
    wrapped_function,
    wrapped_method,
    wrapped_staticmethod,
)
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

    # Collect all TypeVars and ParamSpecs used in functions and class methods
    module_typevars: dict[str, typing.TypeVar | typing.ParamSpec] = {}

    # Extract from standalone functions
    for func in functions:
        annotations = _safe_get_annotations(func)
        func_typevars = _extract_typevars_from_function(func, annotations)
        module_typevars.update(func_typevars)

    # Extract from class methods
    for cls in classes:
        # Extract TypeVars from Generic base class if present (use __orig_bases__)
        bases_to_check = getattr(cls, "__orig_bases__", cls.__bases__)
        for base in bases_to_check:
            origin = typing.get_origin(base)
            if origin is not None and hasattr(origin, "__name__") and origin.__name__ == "Generic":
                args = typing.get_args(base)
                for arg in args:
                    if isinstance(arg, typing.TypeVar) or isinstance(arg, typing.ParamSpec):
                        module_typevars[arg.__name__] = arg

        # Extract TypeVars from method signatures
        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not name.startswith("_"):
                annotations = _safe_get_annotations(method)
                method_typevars = _extract_typevars_from_function(method, annotations)
                module_typevars.update(method_typevars)

    # Generate TypeVar definitions
    if module_typevars:
        typevar_defs = _generate_typevar_definitions(module_typevars, synchronized_types, module.target_module)
        for definition in typevar_defs:
            compiled_code.append(definition)
        compiled_code.append("")  # Add blank line

    # Compile all classes first
    for i, cls in enumerate(classes):
        code = compile_class(cls, module.target_module, synchronizer_name, synchronized_types)
        if i > 0:  # Add blank line before each class except the first
            compiled_code.append("")  # Add blank line (2 newlines when joined)
        compiled_code.append(code)

    # Then compile all functions
    for func in functions:
        # Use the current module's globals (from sys.modules) to get reloaded class objects
        module_globals = sys.modules[func.__module__].__dict__ if func.__module__ in sys.modules else func.__globals__
        code = compile_function(
            func, module.target_module, synchronizer_name, synchronized_types, globals_dict=module_globals
        )
        compiled_code.append(code)
        compiled_code.append("")  # Add blank line

    return "\n".join(compiled_code)


def compile_modules(modules: list[Module], synchronizer_name: str) -> dict[str, str]:
    """
    Compile wrapped items into separate module files.

    Args:
        modules: List of Module instances to compile
        synchronizer_name: Name of the synchronizer

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
