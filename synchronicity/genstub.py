import collections
import collections.abc
import contextlib
import importlib
import inspect
import sys
import typing
from pathlib import Path
from typing import TypeVar, Generic
from unittest import mock

import sigtools.specifiers
from sigtools._signatures import EmptyAnnotation, UpgradedAnnotation

from synchronicity import Interface
from synchronicity.synchronizer import TARGET_INTERFACE_ATTR, SYNCHRONIZER_ATTR


class ReprObj:
    # Hacky repr passthrough object so we can pass verbatim type annotations as partial arguments
    # to generic and have them render correctly through `repr()`, used by inspect.Signature etc.
    def __init__(self, repr: str):
        assert isinstance(repr, str), f"{repr} is not a string!"
        self._repr = repr

    def __repr__(self):
        return self._repr

    def __str__(self):
        return self._repr

    def __call__(self):
        # being a callable gets around some generic's automatic type checking of provided types
        # otherwise we get errors like `provided argument is not a type`
        pass


class StubEmitter:
    def __init__(self, target_module):
        self.target_module = target_module
        self.imports = set()
        self.parts = []
        self._indentation = "    "
        self.global_types = set()
        self.referenced_global_types = set()

    @classmethod
    def from_module(cls, module):
        emitter = cls(module.__name__)
        explicit_members = module.__dict__.get("__all__", [])
        for entity_name, entity in module.__dict__.items():
            if (
                hasattr(entity, "__module__")
                and entity.__module__ != module.__name__
                and entity_name not in explicit_members
            ):
                continue  # skip imported stuff, unless it's explicitly in __all__

            if inspect.isclass(entity):
                emitter.add_class(entity, entity_name)
            elif inspect.isfunction(entity):
                emitter.add_function(entity, entity_name, 0)
            elif isinstance(entity, typing.TypeVar):
                emitter.add_type_var(entity, entity_name)
            elif (
                hasattr(entity, "__class__")
                and getattr(entity.__class__, "__module__", None) == module.__name__
            ):
                # instances of stuff
                emitter.add_variable(entity.__class__, entity_name)

        for varname, annotation in getattr(module, "__annotations__", {}).items():
            emitter.add_variable(annotation, varname)

        return emitter

    def add_variable(self, annotation, name):
        # TODO: evaluate string annotations
        self.parts.append(self._get_var_annotation(name, annotation))

    def add_function(self, func, name, indentation_level=0):
        # adds function source code to module
        self.parts.append(self._get_function_source(func, name, indentation_level))

    def add_class(self, cls, name):
        self.global_types.add(name)
        bases = []
        orig_bases = (
            cls.__orig_bases__ if hasattr(cls, "__orig_bases__") else cls.__bases__
        )  # fix for generic base types
        for b in orig_bases:
            if b is not object:
                # Note: Translation of base types themselves are handled by synchronicity's class wrapping
                # TODO: handle "translation" of Generic type arguments in base classes?
                self._register_imports(b)
                bases.append(self._formatannotation(b))
        bases_str = "" if not bases else "(" + ", ".join(bases) + ")"
        decl = f"class {name}{bases_str}:"
        var_annotations = []
        methods = []

        annotations = cls.__dict__.get("__annotations__", {})
        annotations = {
            k: self._finalize_annotation(annotation, cls)
            for k, annotation in annotations.items()
        }

        body_indent_level = 1
        body_indent = self._indent(body_indent_level)

        for varname, annotation in annotations.items():
            var_annotations.append(
                f"{body_indent}{self._get_var_annotation(varname, annotation)}"
            )
        if var_annotations:
            var_annotations.append(
                ""
            )  # formatting ocd - add an extra newline after var annotations

        for entity_name, entity in cls.__dict__.items():
            if inspect.isfunction(entity):
                methods.append(
                    self._get_function_source(entity, entity_name, body_indent_level)
                )

            elif isinstance(entity, classmethod):
                methods.append(
                    f"{body_indent}@classmethod\n{self._get_function_source(entity.__func__, entity_name, body_indent_level)}"
                )

            elif isinstance(entity, staticmethod):
                methods.append(
                    f"{body_indent}@staticmethod\n{self._get_function_source(entity.__func__, entity_name, body_indent_level)}"
                )

            elif isinstance(entity, property):
                methods.append(
                    f"{body_indent}@property\n{self._get_function_source(entity.fget, entity_name, body_indent_level)}"
                )

        padding = [] if var_annotations or methods else [f"{body_indent}..."]
        self.parts.append(
            "\n".join(
                [
                    decl,
                    *var_annotations,
                    *methods,
                    *padding,
                ]
            )
        )

    def add_type_var(self, type_var, name):
        self.imports.add("typing")
        args = [f'"{name}"']
        if type_var.__bound__:
            translated_bound = self._finalize_annotation(type_var.__bound__, type_var)
            str_annotation = self._formatannotation(translated_bound)
            args.append(f'bound="{str_annotation}"')
        self.global_types.add(name)
        self.parts.append(f'{name} = typing.TypeVar({", ".join(args)})')

    def get_source(self):
        missing_types = self.referenced_global_types - self.global_types
        if missing_types:
            print(
                f"WARNING: {self.target_module} missing the following referenced types, expected to be in module"
            )
            for t in missing_types:
                print(t)
        import_src = "\n".join(sorted(f"import {mod}" for mod in self.imports))
        stubs = "\n\n".join(self.parts)
        return f"{import_src}\n\n{stubs}".lstrip()

    def _ensure_import(self, typ):
        # add import for a single type, non-recursive (See _register_imports)
        # also marks the type name as directly referenced if it's part of the target module
        # so we can sanity check
        module = typ.__module__
        if module not in (self.target_module, "builtins"):
            self.imports.add(module)

        if module in self.target_module:
            if not hasattr(typ, "__name__"):
                # weird special case with Generic subclasses in the target module...
                generic_origin = typ.__origin__
                assert issubclass(generic_origin, Generic)  # noqa
                name = generic_origin.__name__
            else:
                name = typ.__name__
            self.referenced_global_types.add(name)

    def _register_imports(self, type_annotation):
        # recursively makes sure a type and any of its type arguments (for generics) are imported
        origin = getattr(type_annotation, "__origin__", None)
        if origin is None:
            # "scalar" base type
            if hasattr(type_annotation, "__module__"):
                self._ensure_import(type_annotation)
            return

        self._ensure_import(type_annotation)  # import the generic itself's module
        for arg in getattr(type_annotation, "__args__", ()):
            self._register_imports(arg)

    def _finalize_annotation(self, annotation, source_class_or_function):
        # Evalutes string annotations and translates synchronicity types to the correct interface
        # simple version of Python 3.10 inspect.get_annotations() functionality

        # Translate signature annotations:
        # translate type annotations on all synchronicity functions
        # it's done here since there may be postponed evaluated annotations (forward/self refs) that
        # can't be evaluated when the functions are wrapped by the synchronizer

        synchronicity_target_interface = getattr(
            source_class_or_function, TARGET_INTERFACE_ATTR, None
        )
        synchronizer = getattr(source_class_or_function, SYNCHRONIZER_ATTR, None)
        if synchronizer:
            try:
                home_module = getattr(
                    source_class_or_function, synchronizer._original_attr
                ).__module__
            except:
                print(source_class_or_function)
                raise
        else:
            home_module = source_class_or_function.__module__

        return self._finalize_annotation_inner(
            annotation, synchronizer, synchronicity_target_interface, home_module
        )

    def _finalize_annotation_inner(
        self, annotation, synchronizer, synchronicity_target_interface, home_module
    ):
        if isinstance(
            annotation, typing.ForwardRef
        ):  # TypeVars wrap their arguments as ForwardRefs (sometimes?)
            annotation = annotation.__forward_arg__

        if isinstance(annotation, str):
            mod = importlib.import_module(home_module)
            try:
                annotation = eval(annotation, mod.__dict__)
            except NameError:
                # attempt to import
                guessed_module, name = annotation.rsplit(".", 1)
                exec(f"import {guessed_module}", mod.__dict__)  # import first
                annotation = eval(annotation, mod.__dict__)

        annotation = self._map_type_annotation(
            annotation,
            synchronizer=synchronizer,
            interface=synchronicity_target_interface,
            home_module=home_module,
        )

        self._register_imports(annotation)
        return annotation

    def _custom_signature(self, func) -> str:
        """
        We use this instead o str(inspect.Signature()) due to a few issues:
        * Generics with None args are incorrectly encoded as NoneType in str(signature)
        * Some names for stdlib module object types omit the module qualification (notably typing)
        * We might have to stringify annotations to support forward/self references
        * General flexibility like not being able to maintain *comments* in the arg declarations if we want to
        * We intentionally do not use follow_wrapped, since it will override runtime-transformed annotations on a wrapper
        * TypeVars default repr is `~T` instead of `origin_module.T` etc.
        """
        sig = sigtools.specifiers.signature(func)

        if sig.upgraded_return_annotation is not EmptyAnnotation:
            return_annotation = sig.upgraded_return_annotation.source_value()
            return_annotation = self._finalize_annotation(return_annotation, func)
            sig = sig.replace(
                return_annotation=return_annotation,
                upgraded_return_annotation=UpgradedAnnotation.upgrade(
                    return_annotation, func, None
                ),  # not sure if needed
            )

        new_parameters = []
        for param in sig.parameters.values():
            if param.upgraded_annotation is not EmptyAnnotation:
                raw_annotation = param.upgraded_annotation.source_value()
                raw_annotation = self._finalize_annotation(raw_annotation, func)
                new_parameters.append(
                    param.replace(
                        annotation=raw_annotation,
                        upgraded_annotation=UpgradedAnnotation.upgrade(
                            raw_annotation, func, param.name
                        ),  # not sure if needed...
                    )
                )
            else:
                new_parameters.append(param)

        sig = sig.replace(parameters=new_parameters)

        # kind of ugly, but this ensures valid formatting of Generics etc, see docstring above
        with mock.patch("inspect.formatannotation", self._formatannotation):
            return str(sig)

    def _get_var_annotation(self, name, annotation):
        # TODO: how to translate annotation here - we don't know the
        self._register_imports(annotation)
        return f"{name}: {self._formatannotation(annotation, None)}"

    def _formatannotation(self, annotation, base_module=None):
        """modified version of `inspect.formatannotations`
        * Uses verbatim `None` instead of `NoneType` for None-arguments in generic types
        * Doesn't omit `typing.`-module from qualified imports in type names
        * recurses through generic types using ReprObj wrapper
        * ignores base_module (uses self.target_module instead)
        """

        assert (
            base_module is None
        )  # inspect.Signature isn't generally using the base_module arg afaik

        origin = getattr(annotation, "__origin__", None)
        assert not isinstance(
            annotation, typing.ForwardRef
        )  # Forward refs should already have been evaluated!

        if origin is None:
            if annotation == Ellipsis:
                return "..."
            if isinstance(annotation, type) or isinstance(annotation, TypeVar):
                if annotation == None.__class__:  # check for "NoneType"
                    return "None"
                name = (
                    annotation.__qualname__
                    if hasattr(annotation, "__qualname__")
                    else annotation.__name__
                )
                if annotation.__module__ in ("builtins", self.target_module):
                    return name
                return annotation.__module__ + "." + name
            return repr(annotation)
        # generic:
        args = getattr(annotation, "__args__", ())

        formatted_annotation = str(
            annotation.copy_with(
                # ellipsis (...) needs to be passed as is, or it will be reformatted
                tuple(
                    ReprObj(self._formatannotation(arg))
                    if arg != Ellipsis
                    else Ellipsis
                    for arg in args
                )
            )
        )
        # this is a bit ugly, but gets rid of incorrect module qualification of Generic subclasses:
        # TODO: find a better way...
        if formatted_annotation.startswith(self.target_module + "."):
            return formatted_annotation.split(self.target_module + ".", 1)[1]
        return formatted_annotation

    def _indent(self, level):
        return level * self._indentation

    def _get_function_source(self, func, name, indentation_level=0) -> str:
        async_prefix = ""
        if inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func):
            async_prefix = "async "

        signature_indent = self._indent(indentation_level)
        body_indent = self._indent(indentation_level + 1)
        signature = self._custom_signature(func)

        return "\n".join(
            [
                f"{signature_indent}{async_prefix}def {name}{signature}:",
                f"{body_indent}...",
                "",
            ]
        )

    def _map_type_annotation(
        self, type_annotation, synchronizer, interface: Interface, home_module=None
    ):
        # recursively map a nested type annotation to match the output interface
        origin = getattr(type_annotation, "__origin__", None)
        if origin is None:
            # scalar - if type is synchronicity origin type, use the blocking/async version instead
            if synchronizer and hasattr(type_annotation, synchronizer._wrapped_attr):
                return getattr(type_annotation, synchronizer._wrapped_attr)[interface]
            return type_annotation

        args = getattr(type_annotation, "__args__", [])
        mapped_args = tuple(
            self._finalize_annotation_inner(arg, synchronizer, interface, home_module)
            for arg in args
        )
        if interface == Interface.BLOCKING:
            # blocking interface special generic translations:
            if origin == collections.abc.AsyncGenerator:
                return typing.Generator[mapped_args + (None,)]

            if origin == contextlib.AbstractAsyncContextManager:
                return typing.ContextManager[mapped_args]

            if origin == collections.abc.AsyncIterable:
                return typing.Iterable[mapped_args]

            if origin == collections.abc.AsyncIterator:
                return typing.Iterator[mapped_args]

            if origin == collections.abc.Awaitable:
                return mapped_args[0]

            if origin == collections.abc.Coroutine:
                return mapped_args[2]

        return type_annotation.copy_with(mapped_args)


def write_stub(module_path: str):
    mod = importlib.import_module(module_path)
    emitter = StubEmitter.from_module(mod)
    source = emitter.get_source()
    stub_path = Path(mod.__file__).with_suffix(".pyi")
    stub_path.write_text(source)
    return stub_path


if __name__ == "__main__":
    for module_path in sys.argv[1:]:
        out_path = write_stub(module_path)
        print(f"Wrote {out_path}")
