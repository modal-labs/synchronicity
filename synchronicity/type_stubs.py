"""
Improvement Ideas:
* Extract this into its own package, not linked to synchronicity, but with good extension plugs?
* Don't use the wrapped synchronicity types directly, and instead emit stubs based on the root
  implementation types directly (but translated to blocking).
* Let synchronicity emit actual function bodies, to avoid runtime wrapping altogether
"""
import collections
import collections.abc
import contextlib
import importlib
import inspect
from logging import getLogger
import sys
import typing
from pathlib import Path
from typing import TypeVar, Generic
from unittest import mock

import sigtools.specifiers  # type: ignore
from sigtools._signatures import EmptyAnnotation, UpgradedAnnotation, UpgradedParameter  # type: ignore

import synchronicity
from synchronicity import Interface, overload_tracking
from synchronicity import combined_types
from synchronicity.annotations import evaluated_annotation
from synchronicity.synchronizer import (
    TARGET_INTERFACE_ATTR,
    SYNCHRONIZER_ATTR,
    MethodWithAio,
    FunctionWithAio,
)

logger = getLogger(__name__)


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


def add_prefix_arg(arg_name, remove_args=0):
    def inject_arg_func(sig: inspect.Signature):
        parameters = list(sig.parameters.values())
        return sig.replace(
            parameters=[
                UpgradedParameter(arg_name, inspect.Parameter.POSITIONAL_OR_KEYWORD),
                *parameters[remove_args:],
            ]
        )

    return inject_arg_func


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
        for entity_name, entity in module.__dict__.copy().items():
            if (
                hasattr(entity, "__module__")
                and entity.__module__ != module.__name__
                and entity_name not in explicit_members
            ):
                continue  # skip imported stuff, unless it's explicitly in __all__
            if inspect.isclass(entity):
                emitter.add_class(entity, entity_name)
            elif inspect.isfunction(entity) or isinstance(entity, FunctionWithAio):
                emitter.add_function(entity, entity_name, 0)
            elif isinstance(entity, typing.TypeVar):
                emitter.add_type_var(entity, entity_name)
            elif hasattr(entity, "__class__") and getattr(entity.__class__, "__module__", None) == module.__name__:
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
        if isinstance(func, FunctionWithAio):
            # since the original function signature lacks the "self" argument of the "synthetic" Protocol, we inject it
            self.parts.append(self._get_dual_function_source(func, name, indentation_level))
        else:
            self.parts.append(self._get_function_source_with_overloads(func, name, indentation_level))

    def _get_translated_class_bases(self, cls):
        # get __orig_bases__ (__bases__ with potential generic args) for any class
        # note that this has to unwrap the class first in case of synchronicity wrappers,
        # since synchronicity classes don't preserve/translate __orig_bases__.
        # (This is due to __init_subclass__ triggering in odd ways for wrapper classes)

        if TARGET_INTERFACE_ATTR in cls.__dict__:
            # get base classes from origin class instead, to preserve potential Generic base classes
            # which are otherwise stripped by synchronicitys wrappers
            synchronizer = cls.__dict__[SYNCHRONIZER_ATTR]
            impl_cls = cls.__dict__[synchronizer._original_attr]
            target_interface = cls.__dict__[TARGET_INTERFACE_ATTR]
            impl_bases = self._get_translated_class_bases(impl_cls)

            retranslated_bases = []
            for impl_base in impl_bases:
                retranslated_bases.append(
                    self._translate_annotation(impl_base, synchronizer, target_interface, cls.__module__)
                )

            return tuple(retranslated_bases)

        # the case that the annotation is a Generic base class, but *not* a synchronicity wrapped one
        bases = []
        for b in cls.__dict__.get("__orig_bases__", cls.__bases__):
            bases.append(self._translate_global_annotation(b, cls))
        return bases

    def add_class(self, cls, name):
        self.global_types.add(name)
        bases = []
        for b in self._get_translated_class_bases(cls):
            if b is not object:
                bases.append(self._formatannotation(b))

        bases_str = "" if not bases else "(" + ", ".join(bases) + ")"
        decl = f"class {name}{bases_str}:"
        var_annotations = []
        methods = []

        annotations = cls.__dict__.get("__annotations__", {})
        annotations = {k: self._translate_global_annotation(annotation, cls) for k, annotation in annotations.items()}

        body_indent_level = 1
        body_indent = self._indent(body_indent_level)

        for varname, annotation in annotations.items():
            var_annotations.append(f"{body_indent}{self._get_var_annotation(varname, annotation)}")
        if var_annotations:
            var_annotations.append("")  # formatting ocd - add an extra newline after var annotations

        for entity_name, entity in cls.__dict__.items():
            if inspect.isfunction(entity):
                methods.append(self._get_function_source_with_overloads(entity, entity_name, body_indent_level))

            elif isinstance(entity, classmethod):
                fn_source = self._get_function_source_with_overloads(entity.__func__, entity_name, body_indent_level)
                methods.append(f"{body_indent}@classmethod\n{fn_source}")

            elif isinstance(entity, staticmethod):
                fn_source = self._get_function_source_with_overloads(entity.__func__, entity_name, body_indent_level)
                methods.append(f"{body_indent}@staticmethod\n{fn_source}")

            elif isinstance(entity, property):
                fn_source = self._get_function_source_with_overloads(entity.fget, entity_name, body_indent_level)
                methods.append(f"{body_indent}@property\n{fn_source}")

            elif isinstance(entity, FunctionWithAio):
                # Note: FunctionWithAio is used for staticmethods
                methods.append(
                    self._get_dual_function_source(
                        entity,
                        entity_name,
                        body_indent_level,
                    )
                )
            elif isinstance(entity, MethodWithAio):
                if entity._is_classmethod:
                    # Classmethods with type vars on the cls variable don't work with "dual interface functions"
                    # at the moment, so we only output a stub for the blocking interface
                    # TODO(elias): allow dual type stubs as long as no type vars are being used in the class var
                    fn_source = self._get_function_source_with_overloads(entity._func, entity_name, body_indent_level)
                    src = f"{body_indent}@classmethod\n{fn_source}"
                else:
                    src = self._get_dual_function_source(
                        entity,
                        entity_name,
                        body_indent_level,
                    )
                methods.append(src)

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

    def _get_dual_function_source(
        self,
        entity: typing.Union[MethodWithAio, FunctionWithAio],
        entity_name,
        body_indent_level,
    ) -> str:
        if isinstance(entity, FunctionWithAio):
            transform_signature = add_prefix_arg(
                "self"
            )  # signature is moved into a protocol class, so we need a self where there previously was none
        elif entity._is_classmethod:
            # TODO: dual protocol for classmethods having annotated cls attributes
            raise Exception("Not supported")
        else:
            transform_signature = add_prefix_arg("self", 1)
        # Emits type stub for a "dual" function that is both callable and has an .aio callable with an async version
        # Currently this is emitted as a typing.Protocol declaration + instance with a __call__ and aio method
        self.imports.add("typing_extensions")
        # Synchronicity specific blocking + async method
        body_indent = self._indent(body_indent_level)
        # create an inline protocol type, inlining both the blocking and async interfaces:
        blocking_func_source = self._get_function_source_with_overloads(
            entity._func,
            "__call__",
            body_indent_level + 1,
            transform_signature=transform_signature,
        )
        aio_func_source = self._get_function_source_with_overloads(
            entity._aio_func,
            "aio",
            body_indent_level + 1,
            transform_signature=transform_signature,
        )
        protocol_attr = f"""\
{body_indent}class __{entity_name}_spec(typing_extensions.Protocol):
{blocking_func_source}
{aio_func_source}
{body_indent}{entity_name}: __{entity_name}_spec
"""
        return protocol_attr

    def add_type_var(self, type_var, name):
        type_module = type(type_var).__module__
        self.imports.add(type_module)
        args = [f'"{name}"']
        if type_var.__bound__:
            translated_bound = self._translate_global_annotation(type_var.__bound__, type_var)
            str_annotation = self._formatannotation(translated_bound)
            args.append(f'bound="{str_annotation}"')
        self.global_types.add(name)
        type_name = type(type_var).__name__  # could be both ParamSpec and TypeVar
        self.parts.append(f'{name} = {type_module}.{type_name}({", ".join(args)})')

    def get_source(self):
        missing_types = self.referenced_global_types - self.global_types
        if missing_types:
            print(f"WARNING: {self.target_module} missing the following referenced types, expected to be in module")
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

        if module == self.target_module:
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

    def _translate_global_annotation(self, annotation, source_class_or_function):
        # convenience wrapper for _translate_annotation when the translated entity itself
        # determines eval scope and synchronizer target

        # infers synchronizer, target and home_module from an entity (class, function) containing the annotation
        synchronicity_target_interface = getattr(source_class_or_function, TARGET_INTERFACE_ATTR, None)
        synchronizer = getattr(source_class_or_function, SYNCHRONIZER_ATTR, None)
        if synchronizer:
            home_module = getattr(source_class_or_function, synchronizer._original_attr).__module__
        else:
            home_module = source_class_or_function.__module__

        return self._translate_annotation(annotation, synchronizer, synchronicity_target_interface, home_module)

    def _translate_annotation(
        self,
        annotation,
        synchronizer: typing.Optional[synchronicity.Synchronizer],
        synchronicity_target_interface: typing.Optional[Interface],
        home_module: typing.Optional[str],
    ):
        """
        Takes an annotation (type, generic, typevar, forward ref) and applies recursively (in case of generics):
        * eval for string annotations (importing `home_module` to be used as namespace)
        * re-mapping of the annotation to the correct synchronicity target
          (using synchronizer and synchronicity_target_interface)
        * registers imports for all referenced modules
        """
        if isinstance(annotation, typing.ForwardRef):  # TypeVars wrap their arguments as ForwardRefs (sometimes?)
            annotation = annotation.__forward_arg__
        if isinstance(annotation, str):
            try:
                annotation = evaluated_annotation(annotation, declaration_module=home_module)
            except Exception:
                logger.exception(
                    f"Error when evaluating {annotation} in {home_module}. Falling back to string annotation"
                )
                return annotation

        translated_annotation = self._translate_annotation_map_types(
            annotation,
            synchronizer=synchronizer,
            interface=synchronicity_target_interface,
            home_module=home_module,
        )

        self._register_imports(translated_annotation)
        return translated_annotation

    def _translate_annotation_map_types(
        self,
        type_annotation,
        synchronizer: typing.Optional[synchronicity.Synchronizer],
        interface: typing.Optional[Interface],
        home_module: typing.Optional[str] = None,
    ):
        # recursively map a nested type annotation to match the output interface
        origin = getattr(type_annotation, "__origin__", None)
        args = getattr(type_annotation, "__args__", None)

        if origin is None or args is None:
            # TODO(elias): handle translation of un-parameterized async entities, like `Awaitable`
            # scalar - if type is synchronicity origin type, use the blocking/async version instead
            if synchronizer:
                return synchronizer._translate_out(type_annotation, interface)
            return type_annotation

        mapped_args = tuple(self._translate_annotation(arg, synchronizer, interface, home_module) for arg in args)
        if interface == Interface.BLOCKING:
            # blocking interface special generic translations:
            if origin == collections.abc.AsyncGenerator:
                return typing.Generator[mapped_args + (None,)]  # type: ignore

            if origin == contextlib.AbstractAsyncContextManager:
                return combined_types.AsyncAndBlockingContextManager[mapped_args]  # type: ignore

            if origin == collections.abc.AsyncIterable:
                return typing.Iterable[mapped_args]  # type: ignore

            if origin == collections.abc.AsyncIterator:
                return typing.Iterator[mapped_args]  # type: ignore

            if origin == collections.abc.Awaitable:
                return mapped_args[0]

            if origin == collections.abc.Coroutine:
                return mapped_args[2]

        if origin.__module__ not in (
            "typing",
            "collections.abc",
            "contextlib",
        ):  # don't translate built in generics in type annotations, even if they have been synchronicity wrapped
            # for other hierarchy reasons...
            translated_origin = self._translate_annotation(origin, synchronizer, interface, home_module)
            if translated_origin is not origin:
                # special case for synchronicity-translated generics,
                # due to synchronicitys wrappers not being valid generics
                # kind of ugly as it returns a string representation rather than a type...
                str_args = ", ".join(self._formatannotation(arg) for arg in mapped_args)
                return ReprObj(f"{self._formatannotation(translated_origin)}[{str_args}]")

        return type_annotation.copy_with(mapped_args)

    def _custom_signature(self, func, transform_signature=None) -> str:
        """
        We use this instead o str(inspect.Signature()) due to a few issues:
        * Generics with None args are incorrectly encoded as NoneType in str(signature)
        * Some names for stdlib module object types omit the module qualification (notably typing)
        * We might have to stringify annotations to support forward/self references
        * General flexibility like not being able to maintain *comments* in the arg declarations if we want to
        * We intentionally do not use follow_wrapped,
          since it will override runtime-transformed annotations on a wrapper
        * TypeVars default repr is `~T` instead of `origin_module.T` etc.
        """
        sig = sigtools.specifiers.signature(func)

        if sig.upgraded_return_annotation is not EmptyAnnotation:
            raw_return_annotation = sig.upgraded_return_annotation.source_value()
            return_annotation = self._translate_global_annotation(raw_return_annotation, func)
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
                translated_annotation = self._translate_global_annotation(raw_annotation, func)
            elif param.annotation != inspect._empty:
                raw_annotation = param.annotation
                translated_annotation = self._translate_global_annotation(raw_annotation, func)
            else:
                translated_annotation = param.annotation

            new_parameters.append(
                param.replace(
                    annotation=translated_annotation,
                    upgraded_annotation=UpgradedAnnotation.upgrade(
                        translated_annotation, func, param.name
                    ),  # not sure if needed...
                )
            )

        sig = sig.replace(parameters=new_parameters)
        if transform_signature:
            sig = transform_signature(sig)

        # kind of ugly, but this ensures valid formatting of Generics etc, see docstring above
        with mock.patch("inspect.formatannotation", self._formatannotation):
            return str(sig)

    def _get_var_annotation(self, name, annotation):
        # TODO: how to translate annotation here - we don't know the
        self._register_imports(annotation)
        return f"{name}: {self._formatannotation(annotation, None)}"

    def _formatannotation(self, annotation, base_module=None) -> str:
        """modified version of `inspect.formatannotations`
        * Uses verbatim `None` instead of `NoneType` for None-arguments in generic types
        * Doesn't omit `typing.`-module from qualified imports in type names
        * recurses through generic types using ReprObj wrapper
        * ignores base_module (uses self.target_module instead)
        """

        assert base_module is None  # inspect.Signature isn't generally using the base_module arg afaik

        origin = getattr(annotation, "__origin__", None)
        assert not isinstance(annotation, typing.ForwardRef)  # Forward refs should already have been evaluated!
        args = getattr(annotation, "__args__", None)

        if origin is None or not args:
            if annotation == Ellipsis:
                return "..."
            if isinstance(annotation, type) or isinstance(annotation, TypeVar):
                if annotation == None.__class__:  # check for "NoneType"
                    return "None"
                name = (
                    annotation.__qualname__  # type: ignore
                    if hasattr(annotation, "__qualname__")
                    else annotation.__name__
                )
                if annotation.__module__ in ("builtins", self.target_module):
                    return name
                return annotation.__module__ + "." + name
            return repr(annotation)
        # generic:
        try:
            formatted_annotation = str(
                annotation.copy_with(
                    # ellipsis (...) needs to be passed as is, or it will be reformatted
                    tuple(ReprObj(self._formatannotation(arg)) if arg != Ellipsis else Ellipsis for arg in args)
                )
            )
        except Exception:
            raise Exception(f"Could not reformat generic {annotation.__origin__} with arguments {args}")

        formatted_annotation = formatted_annotation.replace(
            "typing.Abstract", "typing."
        )  # fix for Python 3.7 formatting typing.AsyncContextManager as 'typing.AbstractContextManager' etc.
        # this is a bit ugly, but gets rid of incorrect module qualification of Generic subclasses:
        # TODO: find a better way...

        if formatted_annotation.startswith(self.target_module + "."):
            return formatted_annotation.split(self.target_module + ".", 1)[1]
        return formatted_annotation

    def _indent(self, level):
        return level * self._indentation

    def _get_function_source_with_overloads(self, func, name, indentation_level=0, transform_signature=None) -> str:
        signature_indent = self._indent(indentation_level)
        body_indent = self._indent(indentation_level + 1)
        parts = []

        interface = func.__dict__.get(TARGET_INTERFACE_ATTR)

        synchronizer = func.__dict__.get(SYNCHRONIZER_ATTR)
        if interface:
            root_func = func.__dict__[SYNCHRONIZER_ATTR]._translate_in(func)
        else:
            root_func = func

        overloaded_signatures = overload_tracking.get_overloads(root_func)
        for overload_func in overloaded_signatures:
            self.imports.add("typing")
            parts.append(f"{signature_indent}@typing.overload")
            if interface:
                overload_func = synchronizer._wrap(overload_func, interface, name=name)

            parts.append(
                self._get_function_source(
                    overload_func,
                    name,
                    signature_indent,
                    body_indent,
                    transform_signature=transform_signature,
                )
            )

        if not overloaded_signatures:
            # only add the functions complete signatures if there are no stubs
            parts.append(
                self._get_function_source(
                    func,
                    name,
                    signature_indent,
                    body_indent,
                    transform_signature=transform_signature,
                )
            )
        return "\n".join(parts)

    def _get_function_source(
        self,
        func,
        name,
        signature_indent: str,
        body_indent: str,
        transform_signature=None,
    ) -> str:
        async_prefix = ""
        if inspect.iscoroutinefunction(func):
            # note: async prefix should not be used for annotated abstract/stub *async generators*,
            # so we don't check for inspect.isasyncgenfunction since they contain no yield keyword,
            # and would otherwise indicate an awaitable that returns an async generator to static type checkers
            async_prefix = "async "

        signature = self._custom_signature(func, transform_signature)

        return "\n".join(
            [
                f"{signature_indent}{async_prefix}def {name}{signature}:",
                f"{body_indent}...",
                "",
            ]
        )


def write_stub(module_path: str):
    with overload_tracking.patched_overload():
        mod = importlib.import_module(module_path)
        assert mod.__file__ is not None
        emitter = StubEmitter.from_module(mod)
        source = emitter.get_source()
        stub_path = Path(mod.__file__).with_suffix(".pyi")
        stub_path.write_text(source)
        return stub_path


if __name__ == "__main__":
    for module_path in sys.argv[1:]:
        out_path = write_stub(module_path)
        print(f"Wrote {out_path}")
