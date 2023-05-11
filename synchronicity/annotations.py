# compatibility utilities/polyfills for supporting older python versions
import importlib
import sys
import logging

logger = logging.getLogger("synchronicity")


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
            # hack: import the library *into* the namespace of the supplied globals
            exec(f"import {ref_module}", globals_)
            return eval(annotation, globals_)
        raise
