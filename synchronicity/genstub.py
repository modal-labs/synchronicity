import inspect
import types
from unittest import mock

import sigtools.specifiers


class ReprObj:
    # Hacky repr object so we can pass verbatim type annotations as partial arguments
    # to generic and have them render correctly through `repr()`, used by inspect.Signature etc.
    def __init__(self, repr):
        self._repr = repr

    def __repr__(self):
        return self._repr

    def __str__(self):
        return self._repr

    def __call__(self):
        # gets around some generic's automatic type checking of provided types
        # otherwise we get errors like `provided argument is not a type`
        pass


class StubEmitter:
    def __init__(self, target_module):
        self.target_module = target_module
        self.imports = set()
        self.parts = []
        self._indentation = "    "

    @classmethod
    def from_module(cls, module):
        emitter = cls(module.__name__)
        for entity_name, entity in module.__dict__.items():
            if hasattr(entity, "__module__"):
                if entity.__module__ != module.__name__:
                    continue  # skip imported stuff

            if inspect.isclass(entity):
                emitter.add_class(entity, entity_name)
            elif inspect.isfunction(entity):
                emitter.add_function(entity, entity_name, 0)

        for varname, annotation in getattr(module, "__annotations__", {}).items():
            emitter.add_variable(annotation, varname)

        return emitter

    def add_variable(self, annotation, name):
        self.parts.append(self._get_var_annotation(name, annotation))

    def add_function(self, func, name, indentation_level=0):
        # adds function source code to module
        self.parts.append(self._get_function(func, name, indentation_level))

    def add_class(self, cls, name):
        decl = f"class {name}:"
        var_annotations = []
        methods = []

        body_indent_level = 1
        body_indent = self._indent(body_indent_level)
        for varname, annotation in getattr(cls, "__annotations__", {}).items():
            var_annotations.append(
                f"{body_indent}{self._get_var_annotation(varname, annotation)}"
            )

        for entity_name, entity in cls.__dict__.items():
            if inspect.isfunction(entity):
                methods.append(
                    self._get_function(entity, entity_name, body_indent_level)
                )

            elif isinstance(entity, classmethod):
                methods.append(
                    f"{body_indent}@classmethod\n{self._get_function(entity.__func__, entity_name, body_indent_level)}"
                )

            elif isinstance(entity, staticmethod):
                methods.append(
                    f"{body_indent}@staticmethod\n{self._get_function(entity.__func__, entity_name, body_indent_level)}"
                )

            elif isinstance(entity, property):
                methods.append(
                    f"{body_indent}@property\n{self._get_function(entity.fget, entity_name, body_indent_level)}"
                )

        self.parts.append(
            "\n".join(
                [
                    decl,
                    *var_annotations,
                    *methods,
                ]
            )
        )

    def get_source(self):
        import_src = "\n".join(sorted(f"import {mod}" for mod in self.imports))
        stubs = "\n".join(self.parts)
        return f"{import_src}\n\n{stubs}".lstrip()

    def _import_module(self, module: str):
        if module not in (self.target_module, "builtins"):
            self.imports.add(module)

    def _register_imports(self, type_annotation):
        origin = getattr(type_annotation, "__origin__", None)
        if origin is None:
            # "scalar" base type
            self._import_module(type_annotation.__module__)
            return

        self._import_module(
            type_annotation.__module__
        )  # import the generic itself's module
        for arg in getattr(type_annotation, "__args__", ()):
            self._register_imports(arg)

    def _get_func_stub_source(self, func, name, indentation_level):
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

    def _custom_signature(self, func) -> str:
        """
        We use this instead o str(inspect.Signature()) due to a few issues:
        * Generics with None args are incorrectly encoded as NoneType in str(signature)
        * Some names for stdlib module object types omit the module qualification (notably typing)
        * We might have to stringify annotations to support forward/self references
        * General flexibility like not being able to maintain *comments* in the arg declarations if we want to
        * We intentionally do not use follow_wrapped, since it will override runtime-transformed annotations on a wrapper
        """

        # haxx, please rewrite to avoid monkey patch... :'(
        with mock.patch("inspect.formatannotation", self._formatannotation):
            return str(sigtools.specifiers.signature(func))

    def _get_var_annotation(self, name, annotation):
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
        if origin is None:
            if isinstance(annotation, type):
                if annotation == None.__class__:
                    return "None"
                if annotation.__module__ in ("builtins", self.target_module):
                    return annotation.__qualname__
                return annotation.__module__ + "." + annotation.__qualname__
            return repr(annotation)
        # generic:
        args = getattr(annotation, "__args__", ())
        return annotation.copy_with(
            tuple(ReprObj(self._formatannotation(arg)) for arg in args)
        )

    def _indent(self, level):
        return level * self._indentation

    def _get_function(self, func, name, indentation_level=0):
        # return source code of function and track imports
        for annotation in func.__annotations__.values():
            self._register_imports(annotation)

        return self._get_func_stub_source(func, name, indentation_level)
