# compatibility utilities/polyfills for supporting older python versions
import importlib
import inspect
import logging
import sys
import typing

logger = logging.getLogger("synchronicity")

# Modules that cannot be evaluated at runtime, e.g.,
# only available under the TYPE_CHECKING guard, but can be used freely in stub files
TYPE_CHECKING_OVERRIDES = {"_typeshed"}


def evaluated_annotation(annotation, *, globals_=None, declaration_module=None):
    # evaluate string annotations...
    imported_declaration_module = None
    if globals_ is None and declaration_module is not None:
        if declaration_module in sys.modules:
            # already loaded module
            imported_declaration_module = sys.modules[declaration_module]
        else:
            imported_declaration_module = importlib.import_module(declaration_module)
        globals_ = imported_declaration_module.__dict__

    try:
        return eval(annotation, globals_)
    except NameError:
        if "." in annotation:
            # in case of unimported modules referenced in the annotation itself
            # typically happens with TYPE_CHECKING guards etc.
            ref_module, _ = annotation.rsplit(".", 1)
            # for modules that can't be evaluated at runtime,
            # return a ForwardRef with __forward_module__ set
            # to the name of the module that we want to import in the stub file
            if ref_module in TYPE_CHECKING_OVERRIDES:
                ref = typing.ForwardRef(annotation)
                ref.__forward_module__ = ref_module
                return ref
            # hack: import the library *into* the namespace of the supplied globals
            exec(f"import {ref_module}", globals_)
            return eval(annotation, globals_)
        raise


def get_annotations(obj: typing.Any) -> dict:
    # inspect.get_annotations was added in Python 3.10. We only get annotations from
    # functions and class types so we'
    if sys.version_info[:2] <= (3, 9):
        if isinstance(obj, type):
            return obj.__dict__.get("__annotations__", {})
        elif callable(obj):
            # function
            return getattr(obj, "__annotations__", {})
        else:
            raise TypeError(f"{obj!r} is not a class or callable.")
    return inspect.get_annotations(obj)
