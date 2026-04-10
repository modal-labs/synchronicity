"""Emit sync + async (.aio) wrapper source — the default synchronicity wrapper shape."""

from __future__ import annotations

import dataclasses

from ..compile_utils import _build_call_with_wrap, _format_return_annotation, format_parameters_for_emit
from ..ir import (
    ClassWrapperIR,
    MethodBindingKind,
    MethodWrapperIR,
    ModuleCompilationIR,
    ModuleLevelFunctionIR,
    TypeVarSpecIR,
)
from ..sync_registry import SyncRegistry
from ..transformer_ir import ImplQualifiedRef
from ..transformer_materialize import MaterializeContext, materialize_transformer_ir
from ..type_transformer import AwaitableTransformer, CoroutineTransformer
from ..typevar_codegen import typevar_definition_lines


@dataclasses.dataclass(frozen=True)
class MethodEmitOwner:
    """Class-wrapper context needed when emitting method wrappers (emitter-only)."""

    impl_ref: ImplQualifiedRef
    target_module: str


def _wrapper_short_name(impl_ref: ImplQualifiedRef) -> str:
    """Emitted wrapper class identifier (last segment of implementation ``__qualname__``)."""

    return impl_ref.qualname.rpartition(".")[2]


def _wrapper_class_reference_for_emit(
    impl_ref: ImplQualifiedRef,
    sync: SyncRegistry,
    target_module: str,
) -> str:
    """Resolve a wrapped implementation class to the identifier used on a generated class line."""

    wrapper_module, wrapper_name = sync[impl_ref]
    if wrapper_module == target_module:
        return wrapper_name
    return f"{wrapper_module}.{wrapper_name}"


def _impl_type_dotted(impl_ref: ImplQualifiedRef) -> str:
    """Dotted path to the implementation type for emitted source.

    Uses ``module`` + ``.__qualname__`` when qualname is a normal attribute path. If
    ``__qualname__`` contains ``<locals>`` (nested in a function), only the last
    segment is appended so the reference matches the previous
    ``impl_ref.module`` + short-name emission (full qualname is not valid Python).
    """

    q = impl_ref.qualname
    if ".<locals>." in q or q.startswith("<locals>."):
        return f"{impl_ref.module}.{q.rpartition('.')[2]}"
    return f"{impl_ref.module}.{q}"


def method_emit_owner(class_ir: ClassWrapperIR, target_module: str) -> MethodEmitOwner:
    return MethodEmitOwner(impl_ref=class_ir.impl_ref, target_module=target_module)


def _materialize_context_for_module(specs: tuple[TypeVarSpecIR, ...]) -> MaterializeContext | None:
    if not specs:
        return None
    return MaterializeContext(typevar_specs_by_name={s.name: s for s in specs})


_CLASS_INIT_NAME = "__init__"
_ASYNC_ITERATOR_DUNDERS = frozenset({"__aiter__", "__anext__"})


def _partition_class_methods(
    methods: tuple[MethodWrapperIR, ...],
) -> tuple[MethodWrapperIR | None, tuple[MethodWrapperIR, ...], tuple[MethodWrapperIR, ...]]:
    """Split ``__init__``, async-iterator dunders, and everything else for emission order."""

    init_mir: MethodWrapperIR | None = None
    iterator: list[MethodWrapperIR] = []
    normal: list[MethodWrapperIR] = []
    iter_order = {"__aiter__": 0, "__anext__": 1}
    for mir in methods:
        if mir.method_name == _CLASS_INIT_NAME:
            init_mir = mir
        elif mir.method_name in _ASYNC_ITERATOR_DUNDERS:
            iterator.append(mir)
        else:
            normal.append(mir)
    iterator.sort(key=lambda m: iter_order[m.method_name])
    return init_mir, tuple(iterator), tuple(normal)


def _async_iterator_dunder_surfaces(
    impl_dunder: str,
) -> tuple[str, str, bool, bool] | None:
    """Map impl ``__aiter__`` / ``__anext__`` to wrapper sync name, async name, ``async def`` flag, bridge."""
    if impl_dunder == "__aiter__":
        return ("__iter__", "__aiter__", False, False)
    if impl_dunder == "__anext__":
        return ("__next__", "__anext__", True, True)
    return None


def _method_impl_call_expr(
    method_type: MethodBindingKind,
    impl_class_dotted: str,
    method_name: str,
    call_args_str: str,
) -> str:
    impl_class_ref = impl_class_dotted
    if method_type == MethodBindingKind.INSTANCE:
        return f"impl_method(wrapper_instance._impl_instance, {call_args_str})"
    if method_type in (MethodBindingKind.CLASSMETHOD, MethodBindingKind.STATICMETHOD):
        return f"{impl_class_ref}.{method_name}({call_args_str})"
    return f"impl_method(wrapper_instance._impl_instance, {call_args_str})"


def _runtime_import_header(runtime_package: str) -> str:
    return f"""import {runtime_package}.types
from {runtime_package}.descriptor import (
    wrapped_classmethod,
    wrapped_function,
    wrapped_method,
    wrapped_staticmethod,
)
from {runtime_package}.synchronizer import get_synchronizer, _wrapped_from_impl
"""


def emit_module_level_function(
    ir: ModuleLevelFunctionIR,
    sync: SyncRegistry,
    target_module: str,
    runtime_package: str = "synchronicity",
    *,
    mat_ctx: MaterializeContext | None = None,
) -> str:
    current_target_module = target_module
    return_transformer = materialize_transformer_ir(ir.return_transformer_ir, sync, runtime_package, ctx=mat_ctx)
    param_str, call_args_str, unwrap_code = format_parameters_for_emit(
        ir.parameters,
        sync,
        current_target_module,
        runtime_package,
        unwrap_indent="    ",
        mat_ctx=mat_ctx,
    )
    is_async_gen = ir.is_async_gen
    f = ir.impl_ref.qualname.rpartition(".")[2]
    impl_dotted = f"{ir.impl_ref.module}.{f}"

    if not ir.needs_async_wrapper:
        sync_return_str, _ = _format_return_annotation(return_transformer, sync, current_target_module)

        inline_helpers_dict = return_transformer.get_wrapper_helpers(sync, current_target_module, indent="")
        if inline_helpers_dict:
            cleaned_helpers = {}
            for name, helper_code in inline_helpers_dict.items():
                lines = helper_code.split("\n")
                cleaned_lines = []
                for line in lines:
                    if line.strip().startswith("@staticmethod"):
                        continue
                    cleaned_lines.append(line)
                cleaned_helpers[name] = "\n".join(cleaned_lines)
            helpers_code = "\n".join(cleaned_helpers.values())
        else:
            helpers_code = ""

        function_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            sync,
            current_target_module,
            indent="    ",
            is_async=False,
            is_function=True,
        )

        impl_ref = f"    impl_function = {impl_dotted}"
        if unwrap_code:
            function_body = f"{impl_ref}\n{unwrap_code}\n{function_body}"
        else:
            function_body = f"{impl_ref}\n{function_body}"

        function_code = f"""def {f}({param_str}){sync_return_str}:
{function_body}"""

        if helpers_code:
            return f"{helpers_code}\n\n{function_code}"
        return function_code

    sync_return_str, async_return_str = _format_return_annotation(return_transformer, sync, current_target_module)

    inline_helpers_dict = return_transformer.get_wrapper_helpers(sync, current_target_module, indent="    ")

    if isinstance(return_transformer, (AwaitableTransformer, CoroutineTransformer)):
        inner_helpers = return_transformer.return_transformer.get_wrapper_helpers(
            sync, current_target_module, indent="    "
        )
        inline_helpers_dict.update(inner_helpers)
    if inline_helpers_dict:
        cleaned_helpers = {}
        for name, helper_code in inline_helpers_dict.items():
            lines = helper_code.split("\n")
            cleaned_lines = []
            for line in lines:
                if line.strip().startswith("@staticmethod"):
                    continue
                if line.startswith("    "):
                    cleaned_lines.append(line[4:])
                else:
                    cleaned_lines.append(line)
            cleaned_helpers[name] = "\n".join(cleaned_lines)
        helpers_code = "\n".join(cleaned_helpers.values())
    else:
        helpers_code = ""

    aio_function_name = f"__{f}_aio"

    aio_impl_ref = f"    impl_function = {impl_dotted}"
    aio_unwrap_section = aio_impl_ref
    if unwrap_code:
        aio_unwrap_section += "\n" + unwrap_code

    if is_async_gen:
        wrap_expr_raw = return_transformer.wrap_expr(sync, current_target_module, "gen")
        wrap_expr = wrap_expr_raw.replace("self.", "")
        aio_body = (
            f"    gen = impl_function({call_args_str})\n"
            f"    _wrapped = {wrap_expr}\n"
            f"    _sent = None\n"
            f"    try:\n"
            f"        while True:\n"
            f"            try:\n"
            f"                _item = await _wrapped.asend(_sent)\n"
            f"                _sent = yield _item\n"
            f"            except StopAsyncIteration:\n"
            f"                break\n"
            f"    finally:\n"
            f"        await _wrapped.aclose()"
        )
    else:
        aio_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            sync,
            current_target_module,
            indent="    ",
            is_async=True,
            is_function=True,
        )

    async_wrapper_code = f"""async def {aio_function_name}({param_str}){async_return_str}:
{aio_unwrap_section}
{aio_body}
"""

    sync_impl_ref = f"    impl_function = {impl_dotted}"
    sync_unwrap_section = sync_impl_ref
    if unwrap_code:
        sync_unwrap_section += "\n" + unwrap_code

    if is_async_gen:
        sync_wrap_expr_raw = return_transformer.wrap_expr(sync, current_target_module, "gen", is_async=False)
        sync_wrap_expr = sync_wrap_expr_raw.replace("self.", "")
        sync_function_body = f"    gen = impl_function({call_args_str})\n    yield from {sync_wrap_expr}"
    else:
        sync_function_body = _build_call_with_wrap(
            f"impl_function({call_args_str})",
            return_transformer,
            sync,
            current_target_module,
            indent="    ",
            is_async=False,
            is_function=True,
        )

    sync_function_code = f"""@wrapped_function({aio_function_name})
def {f}({param_str}){sync_return_str}:
{sync_unwrap_section}
{sync_function_body}
"""

    if helpers_code:
        return f"{helpers_code}\n\n{async_wrapper_code}{sync_function_code}"
    return f"{async_wrapper_code}{sync_function_code}"


def emit_method_wrapper_pair(
    owner: MethodEmitOwner,
    mir: MethodWrapperIR,
    sync: SyncRegistry,
    *,
    runtime_package: str = "synchronicity",
    mat_ctx: MaterializeContext | None = None,
) -> tuple[str, str]:
    method_name = mir.method_name
    method_type = mir.method_type
    impl_dotted = _impl_type_dotted(owner.impl_ref)
    short_name = _wrapper_short_name(owner.impl_ref)
    current_target_module = owner.target_module
    return_transformer = materialize_transformer_ir(mir.return_transformer_ir, sync, runtime_package, ctx=mat_ctx)
    param_str, call_args_str, unwrap_code = format_parameters_for_emit(
        mir.parameters,
        sync,
        current_target_module,
        runtime_package,
        unwrap_indent="    ",
        mat_ctx=mat_ctx,
    )
    call_expr_prefix = _method_impl_call_expr(
        method_type,
        impl_dotted,
        method_name,
        call_args_str,
    )
    dummy_param_str = param_str
    is_async_gen = mir.is_async_gen
    is_async = mir.is_async
    sync_return_str, async_return_str = _format_return_annotation(return_transformer, sync, current_target_module)

    aio_body = None
    sync_method_body = ""

    if method_type == MethodBindingKind.INSTANCE:
        if not is_async:
            sync_call_expr = call_expr_prefix
            sync_method_body = _build_call_with_wrap(
                sync_call_expr,
                return_transformer,
                sync,
                current_target_module,
                indent="    ",
                is_async=False,
                method_type=method_type,
                method_owner_impl_ref=owner.impl_ref,
            )
            impl_method_line = f"    impl_method = {impl_dotted}.{method_name}"
            if unwrap_code:
                sync_method_body = impl_method_line + "\n" + unwrap_code + "\n" + sync_method_body
            else:
                sync_method_body = impl_method_line + "\n" + sync_method_body
            aio_body = None
        elif is_async_gen:
            gen_call = call_expr_prefix
            wrap_expr_raw = return_transformer.wrap_expr(sync, current_target_module, "gen")
            wrap_expr = wrap_expr_raw.replace("self.", "wrapper_instance.")
            impl_method_line = f"impl_method = {impl_dotted}.{method_name}"
            unwrap_lines = f"\n{unwrap_code}\n" if unwrap_code else "\n"
            aio_body = (
                f"    {impl_method_line}{unwrap_lines}"
                f"    gen = {gen_call}\n"
                f"    _wrapped = {wrap_expr}\n"
                f"    _sent = None\n"
                f"    try:\n"
                f"        while True:\n"
                f"            try:\n"
                f"                _item = await _wrapped.asend(_sent)\n"
                f"                _sent = yield _item\n"
                f"            except StopAsyncIteration:\n"
                f"                break\n"
                f"    finally:\n"
                f"        await _wrapped.aclose()"
            )
            sync_wrap_expr_raw = return_transformer.wrap_expr(sync, current_target_module, "gen", is_async=False)
            sync_wrap_expr = sync_wrap_expr_raw
            impl_method_line_sync = f"    {impl_method_line}"
            if unwrap_code:
                sync_method_body = (
                    f"{impl_method_line_sync}\n{unwrap_code}\n    gen = {gen_call}\n    yield from {sync_wrap_expr}"
                )
            else:
                sync_method_body = f"{impl_method_line_sync}\n    gen = {gen_call}\n    yield from {sync_wrap_expr}"
        else:
            impl_method_line = f"    impl_method = {impl_dotted}.{method_name}"

            aio_body = _build_call_with_wrap(
                call_expr_prefix,
                return_transformer,
                sync,
                current_target_module,
                indent="    ",
                is_async=True,
                method_type=method_type,
                method_owner_impl_ref=owner.impl_ref,
            )
            if unwrap_code:
                aio_body = impl_method_line + "\n" + unwrap_code + "\n" + aio_body
            else:
                aio_body = impl_method_line + "\n" + aio_body

            sync_method_body = _build_call_with_wrap(
                call_expr_prefix,
                return_transformer,
                sync,
                current_target_module,
                indent="    ",
                is_async=False,
                method_type=method_type,
                method_owner_impl_ref=owner.impl_ref,
            )
            if unwrap_code:
                sync_method_body = impl_method_line + "\n" + unwrap_code + "\n" + sync_method_body
            else:
                sync_method_body = impl_method_line + "\n" + sync_method_body
    elif method_type == MethodBindingKind.CLASSMETHOD:
        if not is_async:
            sync_call_expr = call_expr_prefix
            sync_method_body = _build_call_with_wrap(
                sync_call_expr,
                return_transformer,
                sync,
                current_target_module,
                indent="    ",
                is_async=False,
                method_type=method_type,
                method_owner_impl_ref=owner.impl_ref,
            )
            if unwrap_code:
                sync_method_body = unwrap_code + "\n" + sync_method_body
            aio_body = None
        elif is_async_gen:
            gen_call = call_expr_prefix
            wrap_expr_raw = return_transformer.wrap_expr(sync, current_target_module, "gen")
            wrap_expr = wrap_expr_raw.replace("self.", "wrapper_class.")
            unwrap_lines = f"{unwrap_code}\n    " if unwrap_code else ""
            aio_body = (
                f"    {unwrap_lines}gen = {gen_call}\n"
                f"    _wrapped = {wrap_expr}\n"
                f"    _sent = None\n"
                f"    try:\n"
                f"        while True:\n"
                f"            try:\n"
                f"                _item = await _wrapped.asend(_sent)\n"
                f"                _sent = yield _item\n"
                f"            except StopAsyncIteration:\n"
                f"                break\n"
                f"    finally:\n"
                f"        await _wrapped.aclose()"
            )
            sync_wrap_expr_raw = return_transformer.wrap_expr(sync, current_target_module, "gen", is_async=False)
            sync_wrap_expr = sync_wrap_expr_raw
            if unwrap_code:
                sync_method_body = f"{unwrap_code}\n    gen = {gen_call}\n    yield from {sync_wrap_expr}"
            else:
                sync_method_body = f"    gen = {gen_call}\n    yield from {sync_wrap_expr}"
        else:
            aio_body = _build_call_with_wrap(
                call_expr_prefix,
                return_transformer,
                sync,
                current_target_module,
                indent="    ",
                is_async=True,
                method_type=method_type,
                method_owner_impl_ref=owner.impl_ref,
            )
            if unwrap_code:
                aio_body = unwrap_code + "\n" + aio_body

            sync_method_body = _build_call_with_wrap(
                call_expr_prefix,
                return_transformer,
                sync,
                current_target_module,
                indent="    ",
                is_async=False,
                method_type=method_type,
                method_owner_impl_ref=owner.impl_ref,
            )
            if unwrap_code:
                sync_method_body = unwrap_code + "\n" + sync_method_body
    elif method_type == MethodBindingKind.STATICMETHOD:
        if not is_async:
            sync_call_expr = call_expr_prefix
            sync_method_body = _build_call_with_wrap(
                sync_call_expr,
                return_transformer,
                sync,
                current_target_module,
                indent="    ",
                is_async=False,
                method_type=method_type,
                method_owner_impl_ref=owner.impl_ref,
            )
            if unwrap_code:
                sync_method_body = unwrap_code + "\n" + sync_method_body
            aio_body = None
        elif is_async_gen:
            gen_call = call_expr_prefix
            wrap_expr_raw = return_transformer.wrap_expr(sync, current_target_module, "gen")
            if "self." in wrap_expr_raw:
                wrap_expr = wrap_expr_raw.replace("self.", f"{short_name}()._").replace("_(", "(")
            else:
                wrap_expr = wrap_expr_raw
            unwrap_lines = f"{unwrap_code}\n    " if unwrap_code else ""
            aio_body = (
                f"    {unwrap_lines}gen = {gen_call}\n"
                f"    _wrapped = {wrap_expr}\n"
                f"    _sent = None\n"
                f"    try:\n"
                f"        while True:\n"
                f"            try:\n"
                f"                _item = await _wrapped.asend(_sent)\n"
                f"                _sent = yield _item\n"
                f"            except StopAsyncIteration:\n"
                f"                break\n"
                f"    finally:\n"
                f"        await _wrapped.aclose()"
            )
            sync_wrap_expr_raw = return_transformer.wrap_expr(sync, current_target_module, "gen", is_async=False)
            if "self." in sync_wrap_expr_raw:
                sync_wrap_expr = sync_wrap_expr_raw.replace("self.", f"{short_name}()._").replace("_(", "(")
            else:
                sync_wrap_expr = sync_wrap_expr_raw
            if unwrap_code:
                sync_method_body = f"{unwrap_code}\n    gen = {gen_call}\n    yield from {sync_wrap_expr}"
            else:
                sync_method_body = f"    gen = {gen_call}\n    yield from {sync_wrap_expr}"
        else:
            aio_body = _build_call_with_wrap(
                call_expr_prefix,
                return_transformer,
                sync,
                current_target_module,
                indent="    ",
                is_async=True,
                method_type=method_type,
                method_owner_impl_ref=owner.impl_ref,
            )
            if unwrap_code:
                aio_body = unwrap_code + "\n" + aio_body

            sync_method_body = _build_call_with_wrap(
                call_expr_prefix,
                return_transformer,
                sync,
                current_target_module,
                indent="    ",
                is_async=False,
                method_type=method_type,
                method_owner_impl_ref=owner.impl_ref,
            )
            if unwrap_code:
                sync_method_body = unwrap_code + "\n" + sync_method_body

    aio_method_name = f"__{method_name}_aio"

    if method_type == MethodBindingKind.INSTANCE:
        if aio_body is not None:
            aio_body_with_self = aio_body.replace("wrapper_instance", "self")
            aio_body_lines = aio_body_with_self.split("\n")
            aio_body_indented = "\n".join(
                (
                    "        " + line[4:]
                    if line.strip() and len(line) > 4 and line.startswith("    ")
                    else "        " + line.lstrip()
                    if line.strip()
                    else ""
                )
                for line in aio_body_lines
            )
            aio_wrapper_method = (
                f"    async def {aio_method_name}(self, {param_str}){async_return_str}:\n{aio_body_indented}"
            )
            wrapper_functions_code = aio_wrapper_method
        else:
            wrapper_functions_code = ""
            aio_body = None
    elif method_type == MethodBindingKind.CLASSMETHOD:
        if aio_body is not None:
            aio_body_with_cls = aio_body.replace("wrapper_class", "cls")
            aio_body_lines = aio_body_with_cls.split("\n")
            aio_body_indented = "\n".join(
                (
                    "        " + line[4:]
                    if line.strip() and len(line) > 4 and line.startswith("    ")
                    else "        " + line.lstrip()
                    if line.strip()
                    else ""
                )
                for line in aio_body_lines
            )
            aio_wrapper_method = (
                f"    @classmethod\n"
                f"    async def {aio_method_name}(cls, {param_str}){async_return_str}:\n"
                f"{aio_body_indented}"
            )
            wrapper_functions_code = aio_wrapper_method
        else:
            wrapper_functions_code = ""
            aio_body = None
    elif method_type == MethodBindingKind.STATICMETHOD:
        if aio_body is not None:
            aio_body_lines = aio_body.split("\n")
            aio_body_indented = "\n".join(
                (
                    "        " + line[4:]
                    if line.strip() and len(line) > 4 and line.startswith("    ")
                    else "        " + line.lstrip()
                    if line.strip()
                    else ""
                )
                for line in aio_body_lines
            )
            aio_wrapper_method = (
                f"    @staticmethod\n"
                f"    async def {aio_method_name}({param_str}){async_return_str}:\n"
                f"{aio_body_indented}"
            )
            wrapper_functions_code = aio_wrapper_method
        else:
            wrapper_functions_code = ""
            aio_body = None
    else:
        wrapper_functions_code = ""

    if method_type == MethodBindingKind.CLASSMETHOD:
        decorator_func = "wrapped_classmethod"
    elif method_type == MethodBindingKind.STATICMETHOD:
        decorator_func = "wrapped_staticmethod"
    else:
        decorator_func = "wrapped_method"

    if aio_body is not None:
        if method_type == MethodBindingKind.CLASSMETHOD:
            decorator_line = f"@{decorator_func}({aio_method_name})\n    @classmethod"
        elif method_type == MethodBindingKind.STATICMETHOD:
            decorator_line = f"@{decorator_func}({aio_method_name})\n    @staticmethod"
        else:
            decorator_line = f"@{decorator_func}({aio_method_name})"
        if method_type == MethodBindingKind.INSTANCE:
            method_body_lines = sync_method_body.replace("wrapper_instance", "self").split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()
        elif method_type == MethodBindingKind.CLASSMETHOD:
            method_body_lines = sync_method_body.replace("wrapper_class", "cls").split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()
        else:
            method_body_lines = sync_method_body.split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()
    else:
        if method_type == MethodBindingKind.INSTANCE:
            decorator_line = ""
            method_body_lines = sync_method_body.replace("wrapper_instance", "self").split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()
        elif method_type == MethodBindingKind.CLASSMETHOD:
            decorator_line = "@classmethod"
            method_body_lines = sync_method_body.replace("wrapper_class", "cls").split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()
        else:
            decorator_line = "@staticmethod"
            method_body_lines = sync_method_body.split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()

    if method_type in (MethodBindingKind.CLASSMETHOD, MethodBindingKind.STATICMETHOD):
        if method_type == MethodBindingKind.CLASSMETHOD:
            if param_str:
                plain_param_str = f"cls, {param_str}"
            else:
                plain_param_str = "cls"
            def_line = f"    def {method_name}({plain_param_str}){sync_return_str}:"
        else:
            def_line = f"    def {method_name}({dummy_param_str}){sync_return_str}:"
    else:
        if param_str:
            instance_param_str = f"self, {param_str}"
        else:
            instance_param_str = "self"
        def_line = f"    def {method_name}({instance_param_str}){sync_return_str}:"

    if decorator_line:
        sync_method_code = f"    {decorator_line}\n{def_line}\n        {method_body}"
    else:
        sync_method_code = f"{def_line}\n        {method_body}"

    return wrapper_functions_code, sync_method_code


def emit_class_from_ir(
    ir: ClassWrapperIR,
    sync: SyncRegistry,
    target_module: str,
    *,
    runtime_package: str = "synchronicity",
    mat_ctx: MaterializeContext | None = None,
) -> str:
    """Emit wrapper class source from :class:`ClassWrapperIR` (no live implementation objects)."""
    wshort = _wrapper_short_name(ir.impl_ref)
    impl_dot = _impl_type_dotted(ir.impl_ref)
    sync_self = sync.with_impl_ref(ir.impl_ref, target_module, wshort)
    owner = method_emit_owner(ir, target_module)
    init_mir, iterator_mirs, normal_methods = _partition_class_methods(ir.methods)

    all_helpers_dict: dict[str, str] = {}
    for mir in ir.methods:
        return_transformer = materialize_transformer_ir(
            mir.return_transformer_ir, sync_self, runtime_package, ctx=mat_ctx
        )
        all_helpers_dict.update(return_transformer.get_wrapper_helpers(sync_self, target_module, indent="    "))

    helpers_code = "\n".join(all_helpers_dict.values()) if all_helpers_dict else ""
    helpers_section = f"\n{helpers_code}\n" if helpers_code else ""

    method_definitions_with_async: list[str] = []
    for mir in normal_methods:
        wrapper_functions_code, sync_method_code = emit_method_wrapper_pair(
            owner, mir, sync_self, runtime_package=runtime_package, mat_ctx=mat_ctx
        )
        if wrapper_functions_code:
            method_definitions_with_async.append(f"{wrapper_functions_code}\n\n{sync_method_code}")
        else:
            method_definitions_with_async.append(sync_method_code)

    property_definitions = []
    for attr_name, annotation_ir in ir.attributes:
        attr_type_str = ""
        if annotation_ir is not None:
            attr_transformer = materialize_transformer_ir(annotation_ir, sync_self, runtime_package, ctx=mat_ctx)
            attr_type_str = attr_transformer.wrapped_type(sync_self, target_module)
        if attr_type_str:
            property_code = f"""    # Generated properties
    @property
    def {attr_name}(self) -> {attr_type_str}:
        return self._impl_instance.{attr_name}

    @{attr_name}.setter
    def {attr_name}(self, value: {attr_type_str}):
        self._impl_instance.{attr_name} = value"""
        else:
            property_code = f"""    @property
    def {attr_name}(self):
        return self._impl_instance.{attr_name}

    @{attr_name}.setter
    def {attr_name}(self, value):
        self._impl_instance.{attr_name} = value"""
        property_definitions.append(property_code)

    iterator_methods_section = ""
    if iterator_mirs:
        iterator_blocks: list[str] = []
        for mir in iterator_mirs:
            surfaces = _async_iterator_dunder_surfaces(mir.method_name)
            if surfaces is None:
                continue
            sync_method_name, async_method_name, use_async_def, stop_iteration_bridge = surfaces
            method_return_transformer = materialize_transformer_ir(
                mir.return_transformer_ir, sync_self, runtime_package, ctx=mat_ctx
            )
            method_sync_return_str, method_async_return_str = _format_return_annotation(
                method_return_transformer, sync_self, target_module
            )
            method_call_expr = f"{impl_dot}.{mir.method_name}(self._impl_instance)"
            sync_indent = "            " if stop_iteration_bridge else "        "
            sync_body = _build_call_with_wrap(
                method_call_expr,
                method_return_transformer,
                sync_self,
                target_module,
                indent=sync_indent,
                is_async=False,
                method_type=MethodBindingKind.INSTANCE,
                method_owner_impl_ref=ir.impl_ref,
            )
            if stop_iteration_bridge:
                sync_method = f"""    def {sync_method_name}(self){method_sync_return_str}:
        try:
{sync_body}
        except StopAsyncIteration:
            raise StopIteration()"""
            else:
                sync_method = f"""    def {sync_method_name}(self){method_sync_return_str}:
{sync_body}"""
            iterator_blocks.append(sync_method)

            async_body = _build_call_with_wrap(
                method_call_expr,
                method_return_transformer,
                sync_self,
                target_module,
                indent="        ",
                is_async=True,
                method_type=MethodBindingKind.INSTANCE,
                method_owner_impl_ref=ir.impl_ref,
            )
            async_def_keyword = "async def" if use_async_def else "def"
            async_method = f"""    {async_def_keyword} {async_method_name}(self){method_async_return_str}:
{async_body}"""
            iterator_blocks.append(async_method)
        iterator_methods_section = "\n\n".join(iterator_blocks)

    wrapped_base_strings = [
        _wrapper_class_reference_for_emit(base_impl, sync, target_module) for base_impl in ir.wrapped_base_impl_refs
    ]
    from_impl_method = f"""    @classmethod
    def _from_impl(cls, impl_instance: typing.Any) -> "{wshort}":
        \"\"\"Create wrapper from implementation instance, preserving identity via cache.\"\"\"
        return _wrapped_from_impl(cls, impl_instance, cls._instance_cache)"""

    all_bases: list[str] = []
    if wrapped_base_strings:
        all_bases.extend(wrapped_base_strings)
    if ir.generic_type_parameters:
        all_bases.append(f"typing.Generic[{', '.join(ir.generic_type_parameters)}]")

    if all_bases:
        bases_str = ", ".join(all_bases)
        class_declaration = f"""class {wshort}({bases_str}):"""
    else:
        class_declaration = f"""class {wshort}:"""

    if not wrapped_base_strings:
        class_attrs = (
            f"""    \"\"\"Wrapper class for {impl_dot} """
            f"""with sync/async method support\"\"\"

    _instance_cache: weakref.WeakValueDictionary = weakref.WeakValueDictionary()"""
        )
    else:
        class_attrs = f"""    \"\"\"Wrapper class for {impl_dot} with sync/async method support\"\"\""""

    init_sig, init_call, init_unwrap = format_parameters_for_emit(
        init_mir.parameters if init_mir else (),
        sync_self,
        target_module,
        runtime_package,
        unwrap_indent="        ",
        mat_ctx=mat_ctx,
    )
    init_params = f"self, {init_sig}" if init_sig else "self"
    init_method = f"""    def __init__({init_params}):
{init_unwrap}
        self._impl_instance = {impl_dot}({init_call})
        type(self)._instance_cache[id(self._impl_instance)] = self"""

    properties_section = "\n\n".join(property_definitions) if property_definitions else ""
    methods_section = "\n\n".join(method_definitions_with_async) if method_definitions_with_async else ""

    sections = [init_method]
    if from_impl_method:
        sections.append(from_impl_method)
    if properties_section:
        sections.append(properties_section)
    if iterator_methods_section:
        sections.append(iterator_methods_section)
    if methods_section:
        sections.append(methods_section)

    sections_combined = "\n\n".join(sections)

    wrapper_class_code = f"""{class_declaration}
{class_attrs}{helpers_section}

{sections_combined}"""

    return wrapper_class_code


class SyncAsyncWrapperEmitter:
    """Default emitter: blocking wrappers + hidden ``__*_aio`` async implementations."""

    def __init__(self, runtime_package: str = "synchronicity"):
        self.runtime_package = runtime_package

    def emit_module(
        self,
        ir: ModuleCompilationIR,
        sync: SyncRegistry,
    ) -> str:
        runtime_package = self.runtime_package
        imports = "\n".join(f"import {mod}" for mod in sorted(ir.impl_modules))
        cross_module_import_strs = [f"import {m}" for m in sorted(ir.cross_module_imports.keys())]
        cross_module_imports_str = "\n".join(cross_module_import_strs) if cross_module_import_strs else ""

        header = f"""import typing

{imports}

{_runtime_import_header(runtime_package)}_synchronizer = get_synchronizer({repr(ir.synchronizer_name)})

"""

        if cross_module_imports_str:
            header += f"{cross_module_imports_str}\n"

        compiled_code = [header]

        if ir.has_wrapped_classes:
            compiled_code.append("import weakref")
            compiled_code.append("")

        if ir.typevar_specs:
            for definition in typevar_definition_lines(ir.typevar_specs):
                compiled_code.append(definition)
            compiled_code.append("")

        module_mat_ctx = _materialize_context_for_module(ir.typevar_specs)
        for i, cw in enumerate(ir.class_wrappers):
            code = emit_class_from_ir(
                cw, sync, ir.target_module, runtime_package=runtime_package, mat_ctx=module_mat_ctx
            )
            if i > 0:
                compiled_code.append("")
            compiled_code.append(code)

        for func_ir in ir.module_functions_ir:
            code = emit_module_level_function(
                func_ir,
                sync,
                ir.target_module,
                runtime_package=runtime_package,
                mat_ctx=module_mat_ctx,
            )
            compiled_code.append(code)
            compiled_code.append("")

        return "\n".join(compiled_code)
