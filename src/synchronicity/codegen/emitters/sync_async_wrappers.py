"""Emit sync + async (.aio) wrapper source — the default synchronicity wrapper shape."""

from __future__ import annotations

from ..compile_utils import _build_call_with_wrap, _format_return_annotation, format_parameters_for_emit
from ..ir import ClassWrapperIR, MethodWrapperIR, ModuleCompilationIR, ModuleLevelFunctionIR
from ..sync_registry import SyncRegistry
from ..transformer_materialize import materialize_transformer_ir
from ..type_transformer import AwaitableTransformer, CoroutineTransformer
from ..typevar_codegen import typevar_definition_lines


def _method_impl_call_expr(
    method_type: str,
    origin_module: str,
    class_name: str,
    method_name: str,
    call_args_str: str,
) -> str:
    impl_class_ref = f"{origin_module}.{class_name}"
    if method_type == "instance":
        return f"impl_method(wrapper_instance._impl_instance, {call_args_str})"
    if method_type in ("classmethod", "staticmethod"):
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
) -> str:
    origin_module = ir.origin_module
    current_target_module = target_module
    return_transformer = materialize_transformer_ir(ir.return_transformer_ir, sync, runtime_package)
    param_str, call_args_str, unwrap_code = format_parameters_for_emit(
        ir.parameters,
        sync,
        current_target_module,
        runtime_package,
        unwrap_indent="    ",
    )
    is_async_gen = ir.is_async_gen
    f = ir.impl_name

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

        impl_ref = f"    impl_function = {origin_module}.{f}"
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

    aio_impl_ref = f"    impl_function = {origin_module}.{f}"
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

    sync_impl_ref = f"    impl_function = {origin_module}.{f}"
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
    ir: MethodWrapperIR,
    sync: SyncRegistry,
    *,
    runtime_package: str = "synchronicity",
) -> tuple[str, str]:
    method_name = ir.method_name
    method_type = ir.method_type
    origin_module = ir.origin_module
    class_name = ir.class_name
    current_target_module = ir.current_target_module
    return_transformer = materialize_transformer_ir(ir.return_transformer_ir, sync, runtime_package)
    param_str, call_args_str, unwrap_code = format_parameters_for_emit(
        ir.parameters,
        sync,
        current_target_module,
        runtime_package,
        unwrap_indent="    ",
    )
    call_expr_prefix = _method_impl_call_expr(
        method_type,
        origin_module,
        class_name,
        method_name,
        call_args_str,
    )
    dummy_param_str = param_str
    is_async_gen = ir.is_async_gen
    is_async = ir.is_async
    sync_return_str, async_return_str = _format_return_annotation(return_transformer, sync, current_target_module)

    aio_body = None
    sync_method_body = ""

    if method_type == "instance":
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
                method_owner_impl_ref=ir.owner_impl_ref,
            )
            impl_method_line = f"    impl_method = {origin_module}.{class_name}.{method_name}"
            if unwrap_code:
                sync_method_body = impl_method_line + "\n" + unwrap_code + "\n" + sync_method_body
            else:
                sync_method_body = impl_method_line + "\n" + sync_method_body
            aio_body = None
        elif is_async_gen:
            gen_call = call_expr_prefix
            wrap_expr_raw = return_transformer.wrap_expr(sync, current_target_module, "gen")
            wrap_expr = wrap_expr_raw.replace("self.", "wrapper_instance.")
            impl_method_line = f"impl_method = {origin_module}.{class_name}.{method_name}"
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
            impl_method_line = f"    impl_method = {origin_module}.{class_name}.{method_name}"

            aio_body = _build_call_with_wrap(
                call_expr_prefix,
                return_transformer,
                sync,
                current_target_module,
                indent="    ",
                is_async=True,
                method_type=method_type,
                method_owner_impl_ref=ir.owner_impl_ref,
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
                method_owner_impl_ref=ir.owner_impl_ref,
            )
            if unwrap_code:
                sync_method_body = impl_method_line + "\n" + unwrap_code + "\n" + sync_method_body
            else:
                sync_method_body = impl_method_line + "\n" + sync_method_body
    elif method_type == "classmethod":
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
                method_owner_impl_ref=ir.owner_impl_ref,
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
                method_owner_impl_ref=ir.owner_impl_ref,
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
                method_owner_impl_ref=ir.owner_impl_ref,
            )
            if unwrap_code:
                sync_method_body = unwrap_code + "\n" + sync_method_body
    elif method_type == "staticmethod":
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
                method_owner_impl_ref=ir.owner_impl_ref,
            )
            if unwrap_code:
                sync_method_body = unwrap_code + "\n" + sync_method_body
            aio_body = None
        elif is_async_gen:
            gen_call = call_expr_prefix
            wrap_expr_raw = return_transformer.wrap_expr(sync, current_target_module, "gen")
            if "self." in wrap_expr_raw:
                wrap_expr = wrap_expr_raw.replace("self.", f"{class_name}()._").replace("_(", "(")
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
                sync_wrap_expr = sync_wrap_expr_raw.replace("self.", f"{class_name}()._").replace("_(", "(")
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
                method_owner_impl_ref=ir.owner_impl_ref,
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
                method_owner_impl_ref=ir.owner_impl_ref,
            )
            if unwrap_code:
                sync_method_body = unwrap_code + "\n" + sync_method_body

    aio_method_name = f"__{method_name}_aio"

    if method_type == "instance":
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
    elif method_type == "classmethod":
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
    elif method_type == "staticmethod":
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

    if method_type == "classmethod":
        decorator_func = "wrapped_classmethod"
    elif method_type == "staticmethod":
        decorator_func = "wrapped_staticmethod"
    else:
        decorator_func = "wrapped_method"

    if aio_body is not None:
        if method_type == "classmethod":
            decorator_line = f"@{decorator_func}({aio_method_name})\n    @classmethod"
        elif method_type == "staticmethod":
            decorator_line = f"@{decorator_func}({aio_method_name})\n    @staticmethod"
        else:
            decorator_line = f"@{decorator_func}({aio_method_name})"
        if method_type == "instance":
            method_body_lines = sync_method_body.replace("wrapper_instance", "self").split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()
        elif method_type == "classmethod":
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
        if method_type == "instance":
            decorator_line = ""
            method_body_lines = sync_method_body.replace("wrapper_instance", "self").split("\n")
            method_body = "\n".join(
                "        " + line.lstrip() if line.strip() else "" for line in method_body_lines
            ).strip()
        elif method_type == "classmethod":
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

    if method_type in ("classmethod", "staticmethod"):
        if method_type == "classmethod":
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
    *,
    runtime_package: str = "synchronicity",
) -> str:
    """Emit wrapper class source from :class:`ClassWrapperIR` (no live implementation objects)."""
    sync_self = sync.with_impl_ref(ir.impl_ref, ir.current_target_module, ir.wrapper_class_name)
    all_helpers_dict: dict[str, str] = {}

    for mir in ir.methods:
        return_transformer = materialize_transformer_ir(mir.return_transformer_ir, sync_self, runtime_package)
        all_helpers_dict.update(
            return_transformer.get_wrapper_helpers(sync_self, ir.current_target_module, indent="    ")
        )

    for spec in ir.iterator_methods:
        return_transformer = materialize_transformer_ir(spec.return_transformer_ir, sync_self, runtime_package)
        all_helpers_dict.update(
            return_transformer.get_wrapper_helpers(sync_self, ir.current_target_module, indent="    ")
        )

    helpers_code = "\n".join(all_helpers_dict.values()) if all_helpers_dict else ""
    helpers_section = f"\n{helpers_code}\n" if helpers_code else ""

    method_definitions_with_async: list[str] = []
    for mir in ir.methods:
        wrapper_functions_code, sync_method_code = emit_method_wrapper_pair(
            mir, sync_self, runtime_package=runtime_package
        )
        if wrapper_functions_code:
            method_definitions_with_async.append(f"{wrapper_functions_code}\n\n{sync_method_code}")
        else:
            method_definitions_with_async.append(sync_method_code)

    property_definitions = []
    for attr_name, attr_type in ir.attributes:
        if attr_type:
            property_code = f"""    # Generated properties
    @property
    def {attr_name}(self) -> {attr_type}:
        return self._impl_instance.{attr_name}

    @{attr_name}.setter
    def {attr_name}(self, value: {attr_type}):
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
    if ir.iterator_methods:
        iterator_blocks: list[str] = []
        for spec in ir.iterator_methods:
            method_return_transformer = materialize_transformer_ir(
                spec.return_transformer_ir, sync_self, runtime_package
            )
            method_sync_return_str, method_async_return_str = _format_return_annotation(
                method_return_transformer, sync_self, ir.current_target_module
            )
            method_call_expr = (
                f"{ir.origin_module}.{ir.wrapper_class_name}.{spec.impl_method_name}(self._impl_instance)"
            )
            sync_indent = "            " if spec.stop_iteration_bridge else "        "
            sync_body = _build_call_with_wrap(
                method_call_expr,
                method_return_transformer,
                sync_self,
                ir.current_target_module,
                indent=sync_indent,
                is_async=False,
                method_type="instance",
                method_owner_impl_ref=ir.impl_ref,
            )
            if spec.stop_iteration_bridge:
                sync_method = f"""    def {spec.sync_method_name}(self){method_sync_return_str}:
        try:
{sync_body}
        except StopAsyncIteration:
            raise StopIteration()"""
            else:
                sync_method = f"""    def {spec.sync_method_name}(self){method_sync_return_str}:
{sync_body}"""
            iterator_blocks.append(sync_method)

            async_body = _build_call_with_wrap(
                method_call_expr,
                method_return_transformer,
                sync_self,
                ir.current_target_module,
                indent="        ",
                is_async=True,
                method_type="instance",
                method_owner_impl_ref=ir.impl_ref,
            )
            async_def_keyword = "async def" if spec.use_async_def else "def"
            async_method = f"""    {async_def_keyword} {spec.async_method_name}(self){method_async_return_str}:
{async_body}"""
            iterator_blocks.append(async_method)
        iterator_methods_section = "\n\n".join(iterator_blocks)

    wrapped_bases = list(ir.wrapped_base_names)
    if not wrapped_bases:
        from_impl_method = f"""    @classmethod
    def _from_impl(cls, impl_instance: {ir.origin_module}.{ir.wrapper_class_name}) -> "{ir.wrapper_class_name}":
        \"\"\"Create wrapper from implementation instance, preserving identity via cache.\"\"\"
        return _wrapped_from_impl(cls, impl_instance, cls._instance_cache)"""
    else:
        from_impl_method = ""

    all_bases: list[str] = []
    if wrapped_bases:
        all_bases.extend(wrapped_bases)
    if ir.generic_base:
        all_bases.append(ir.generic_base)

    if all_bases:
        bases_str = ", ".join(all_bases)
        class_declaration = f"""class {ir.wrapper_class_name}({bases_str}):"""
    else:
        class_declaration = f"""class {ir.wrapper_class_name}:"""

    if not wrapped_bases:
        class_attrs = (
            f"""    \"\"\"Wrapper class for {ir.origin_module}.{ir.wrapper_class_name} """
            f"""with sync/async method support\"\"\"

    _instance_cache: weakref.WeakValueDictionary = weakref.WeakValueDictionary()"""
        )
    else:
        class_attrs = f"""    \"\"\"Wrapper class for {ir.origin_module}.{ir.wrapper_class_name} with sync/async method support\"\"\""""

    init_sig, init_call, init_unwrap = format_parameters_for_emit(
        ir.init_parameters,
        sync_self,
        ir.current_target_module,
        runtime_package,
        unwrap_indent="        ",
    )
    init_params = f"self, {init_sig}" if init_sig else "self"
    init_method = f"""    def __init__({init_params}):
{init_unwrap}
        self._impl_instance = {ir.origin_module}.{ir.wrapper_class_name}({init_call})
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

        for i, cw in enumerate(ir.class_wrappers):
            code = emit_class_from_ir(cw, sync, runtime_package=runtime_package)
            if i > 0:
                compiled_code.append("")
            compiled_code.append(code)

        for func_ir in ir.module_functions_ir:
            code = emit_module_level_function(func_ir, sync, ir.target_module, runtime_package=runtime_package)
            compiled_code.append(code)
            compiled_code.append("")

        return "\n".join(compiled_code)
