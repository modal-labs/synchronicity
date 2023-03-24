import inspect


class StubEmitter:
    def __init__(self, target_module):
        self.target_module = target_module
        self.imports = set()
        self.parts = []

    def indent(self, indent):
        return indent * "    "
    def add_function(self, func, indent=0):
        sig = inspect.signature(func)
        for annotation in func.__annotations__.values():
            self._type_imports(annotation)

        self.parts.append(f"def {func.__name__}{sig}:\n{self.indent(indent + 1)}...\n")
    def _import_module(self, module: str):
        if module not in (self.target_module, "builtins"):
            self.imports.add(module)
    def _type_imports(self, type_annotation):
        origin = getattr(type_annotation, "__origin__", None)
        if origin is None:
            # "scalar" base type
            self._import_module(type_annotation.__module__)
            return

        self._import_module(type_annotation.__module__)  # import the generic itself's module
        for arg in getattr(type_annotation, "__args__", ()):
            self._type_imports(arg)

    def get_source(self):
        import_src = "\n".join(sorted(f"import {mod}" for mod in self.imports))
        stubs = "\n\n".join(self.parts)
        return f"{import_src}\n\n{stubs}".lstrip()
