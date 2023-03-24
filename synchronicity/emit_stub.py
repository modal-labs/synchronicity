import collections
import contextlib
import inspect
import typing
from collections import defaultdict
from contextlib import asynccontextmanager as _asynccontextmanager
from inspect import isclass

import synchronicity
from synchronicity import Interface
from synchronicity.synchronizer import INTERFACE_ATTR

synchronizer = synchronicity.Synchronizer()


class _Bar:
    async def bar(self) -> None:
        pass


YIELD_TYPE = typing.TypeVar("YIELD_TYPE")
SEND_TYPE = typing.TypeVar("SEND_TYPE")
def asynccontextmanager(f: typing.AsyncGenerator[YIELD_TYPE, SEND_TYPE]) -> typing.Callable[[], typing.AsyncContextManager[YIELD_TYPE]]:
    acm_factory = _asynccontextmanager(f)
    # TODO: double check first in case stdlib fixes their type forwarding...
    old_ret = acm_factory.__annotations__.pop("return")
    acm_factory.__annotations__["return"] = typing.AsyncContextManager[old_ret.__args__[0]]
    return acm_factory


class _Foo:
    async def foo(self) -> _Bar:
        return _Bar()

    async def nisse(self) -> typing.AsyncGenerator[str, None]:
        yield "hej"

    @asynccontextmanager
    def do_stuff(self) -> typing.AsyncGenerator[_Bar, None]:
        yield _Bar()


def async_to_blocking_type(type_annotation):
    if not hasattr(type_annotation, "__origin__"):
        return type_annotation

    # generic, possibly async
    orig = type_annotation.__origin__
    args = type_annotation.__args__

    translated_args = [async_to_blocking_type(a) for a in args]
    if orig == collections.abc.AsyncGenerator:
        assert len(translated_args) == 2
        return typing.Generator[translated_args[0], translated_args[1], None]  # blocking generators have an extra arg
    if orig == contextlib.AbstractAsyncContextManager:
        assert len(translated_args) == 1
        return typing.ContextManager[translated_args[0]]


def printable_type(type_annotation) -> tuple[set[str], str]:
    # returns set of required imports + printable type
    if not hasattr(type_annotation, "__origin__"):
        # basic types
        if hasattr(type_annotation, "__module__"):
            mod = type_annotation.__module__
            if mod in ("builtin", "__main__"):
                return set(), type_annotation
            else:
                return {mod}, type_annotation
        if type_annotation is None:
            return set(), None
        print(repr(type_annotation), str(type_annotation))
        if repr(type_annotation) == "NoneType":
            return set(), None
        return type_annotation

    return set(), type_annotation


class Registry:
    def __init__(self):
        self.modules = defaultdict(dict)

    def splitmod(self, path):
        if "." in path:
            return path.rsplit(".", 1)
        return "", path

    def create_blocking(self, obj, qualname: str):
        mod, name = self.splitmod(qualname)
        wrapped = synchronizer.create_blocking(obj, name)
        assert name not in self.modules[mod]
        self.modules[mod][name] = wrapped

    def create_async(self, obj, qualname: str):
        mod, name = self.splitmod(qualname)
        wrapped = synchronizer.create_async(obj, name)
        assert name not in self.modules[mod]
        self.modules[mod][name] = wrapped

    def translate_annotation(self, orig_type, interface):
        if interface == Interface.ASYNC:
            newtype = orig_type
        else:
            newtype = async_to_blocking_type(orig_type)

        return rec_type_translation()

    def emit_stub_function(self, name, obj, interface, indent):
        pref = "async " if interface == Interface.ASYNC else ""
        sig = inspect.signature(obj)
        ret = sig.return_annotation
        imports, translated_ret_type = self.translate_annotation(ret, interface)
        translated_params = []
        new_params = []
        for p in sig.parameters.values():
            imp, ref = self.translate_annotation(p.annotation, interface)
            new_params.append(p.replace(annotation=ref))
            imports |= imp
            translated_params.append(ref)

        newsig = sig.replace(parameters=new_params, return_annotation=translated_ret_type)
        return imports, "    " * indent + f"{pref}def {name}{newsig}:\n" + "    " * (indent + 1) + "..."

    def emit_stub_class(self, name: str, obj, interface: Interface, imports_mut: set[str]):
        t_bases = []
        for b in obj.__bases__:
            if b is object:
                continue
            t_bases.append(self.translate_annotation(b, interface, imports_mut))

        bases = ", ".join([str(x) for x in t_bases])
        parts = [
            f"class {name}({bases}):\n"
            f"    # generated from {obj.__qualname__}"
        ]
        all_imports = set()
        for entry_name, entry in obj.__dict__.items():
            if inspect.isfunction(entry):
                entry_imports, entry_source = self.emit_stub_function(entry_name, entry, interface, indent=1)
                all_imports |= entry_imports
                parts.append(entry_source)
        return all_imports, "\n".join(parts)

    def emit_stub_module(self, module: str) -> str:
        source_entries = []
        imports = set()
        for name, wrapped_obj in self.modules[module].items():
            interface = wrapped_obj.__dict__[INTERFACE_ATTR]
            original = wrapped_obj.__dict__[synchronizer._original_attr]

            if isclass(original):
                imp, source = self.emit_stub_class(name, original, interface)
                imports |= imp
                source_entries.append(source)

        parts = [
            f"# module '{module}':",
        ]
        if imports:
            parts.append("\n".join([f"import {x}" for x in imports]))

        parts.append("\n\n".join(source_entries))
        return "\n".join(parts)

    def synchronize_apis(self, obj, blocking_qualname, async_qualname):
        b = self.create_blocking(obj, qualname=blocking_qualname)
        a = self.create_async(obj, qualname=async_qualname)
        return (b, a)

if __name__ == "__main__":
    """Notes:
    Emitted types need to have their names and locations registered somewhere
    in order to generate their type stubs correctly, since the generated stubs
    may refer to other types which should also be translated to their new names/import paths
    """
    r = Registry()
    Bar, AioBar = r.synchronize_apis(_Bar, "bar.Bar", "aio.bar.AioBar")
    Foo, AioFoo = r.synchronize_apis(_Foo, "foo.Foo", "aio.foo.AioFoo")

    for mod in r.modules.keys():
        print(r.emit_stub_module(mod))
        print()
