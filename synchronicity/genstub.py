import inspect
import types
from unittest import mock


class ReprObj:
    def __init__(self, repr):
        self._repr = repr

    def __repr__(self):
        return self._repr

    def __str__(self):
        return self._repr


class StubEmitter:
    def __init__(self, target_module):
        self.target_module = target_module
        self.imports = set()
        self.parts = []
        self._indentation = "    "

    def formatannotation(self, annotation, base_module=None):
        # modified version of the stdlib formatannotations:
        assert (
            base_module is None
        )  # don't think this arg is used by signature, but lets check

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
            tuple(ReprObj(self.formatannotation(arg)) for arg in args)
        )

    def indent(self, level):
        return level * self._indentation

    def _get_function(self, func, name, indentation_level=0):
        # return source code of function and track imports
        for annotation in func.__annotations__.values():
            self._type_imports(annotation)

        return self._get_func_stub_source(func, name, indentation_level)

    def add_function(self, func, name, indentation_level=0):
        # adds function source code to module
        self.parts.append(self._get_function(func, name, indentation_level))

    def _import_module(self, module: str):
        if module not in (self.target_module, "builtins"):
            self.imports.add(module)

    def _type_imports(self, type_annotation):
        origin = getattr(type_annotation, "__origin__", None)
        if origin is None:
            # "scalar" base type
            self._import_module(type_annotation.__module__)
            return

        self._import_module(
            type_annotation.__module__
        )  # import the generic itself's module
        for arg in getattr(type_annotation, "__args__", ()):
            self._type_imports(arg)

    def get_source(self):
        import_src = "\n".join(sorted(f"import {mod}" for mod in self.imports))
        stubs = "\n".join(self.parts)
        return f"{import_src}\n\n{stubs}".lstrip()

    def _get_func_stub_source(self, func, name, indentation_level):
        async_prefix = ""
        if inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func):
            async_prefix = "async "

        signature_indent = self.indent(indentation_level)
        body_indent = self.indent(indentation_level + 1)
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
        """

        # haxx, please rewrite :'(
        with mock.patch("inspect.formatannotation", self.formatannotation):
            return str(inspect.signature(func))

    def add_class(self, cls):
        decl = f"class {cls.__name__}:"
        vars = []
        methods = []

        indent = self.indent(1)
        for varname, annotation in getattr(cls, "__annotations__", {}).items():
            vars.append(f"{indent}{varname}: {self.formatannotation(annotation, None)}")

        for entity_name, entity in cls.__dict__.items():
            if inspect.isfunction(entity):
                methods.append(self._get_function(entity, entity_name, 1))

            elif isinstance(entity, classmethod):
                methods.append(
                    f"{indent}@classmethod\n{self._get_function(entity.__func__, entity_name, 1)}"
                )

            elif isinstance(entity, staticmethod):
                methods.append(
                    f"{indent}@staticmethod\n{self._get_function(entity.__func__, entity_name, 1)}"
                )

            elif isinstance(entity, property):
                methods.append(
                    f"{indent}@property\n{self._get_function(entity.fget, entity_name, 1)}"
                )

        self.parts.append(
            "\n".join(
                [
                    decl,
                    *vars,
                    *methods,
                ]
            )
        )
