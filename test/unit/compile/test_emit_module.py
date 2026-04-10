"""Unit tests for IR → full module emission (``SyncAsyncWrapperEmitter.emit_module``)."""

from __future__ import annotations

import re

from synchronicity.codegen.emitters.sync_async_wrappers import SyncAsyncWrapperEmitter
from synchronicity.codegen.ir import (
    ClassWrapperIR,
    MethodBindingKind,
    MethodWrapperIR,
    ModuleCompilationIR,
    ParameterIR,
)
from synchronicity.codegen.sync_registry import SyncRegistry
from synchronicity.codegen.transformer_ir import (
    AwaitableTypeIR,
    DictTypeIR,
    IdentityTypeIR,
    ImplQualifiedRef,
    ListTypeIR,
    OptionalTypeIR,
)

IMPL = __name__
TARGET = "test_module"

IR_MODULE_TWO_CLASSES = ModuleCompilationIR(
    target_module="test_module",
    synchronizer_name="default_synchronizer",
    impl_modules=frozenset({IMPL}),
    cross_module_imports={},
    typevar_specs=(),
    class_wrappers=(
        ClassWrapperIR(
            impl_ref=ImplQualifiedRef(IMPL, "EmitModuleClassA"),
            wrapped_base_impl_refs=(),
            generic_type_parameters=None,
            attributes=(),
            methods=(
                MethodWrapperIR(
                    method_name="__init__",
                    method_type=MethodBindingKind.INSTANCE,
                    parameters=(
                        ParameterIR(
                            name="value", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None
                        ),
                    ),
                    is_async_gen=False,
                    is_async=False,
                    return_transformer_ir=IdentityTypeIR(signature_text=""),
                ),
                MethodWrapperIR(
                    method_name="get_value",
                    method_type=MethodBindingKind.INSTANCE,
                    parameters=(),
                    is_async_gen=False,
                    is_async=True,
                    return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="int")),
                ),
            ),
        ),
        ClassWrapperIR(
            impl_ref=ImplQualifiedRef(IMPL, "EmitModuleClassB"),
            wrapped_base_impl_refs=(),
            generic_type_parameters=None,
            attributes=(),
            methods=(
                MethodWrapperIR(
                    method_name="__init__",
                    method_type=MethodBindingKind.INSTANCE,
                    parameters=(
                        ParameterIR(
                            name="data",
                            kind=1,
                            annotation_ir=ListTypeIR(item=IdentityTypeIR(signature_text="str")),
                            default_repr=None,
                        ),
                    ),
                    is_async_gen=False,
                    is_async=False,
                    return_transformer_ir=IdentityTypeIR(signature_text=""),
                ),
                MethodWrapperIR(
                    method_name="process_data",
                    method_type=MethodBindingKind.INSTANCE,
                    parameters=(
                        ParameterIR(
                            name="config",
                            kind=1,
                            annotation_ir=DictTypeIR(
                                key=IdentityTypeIR(signature_text="str"), value=IdentityTypeIR(signature_text="int")
                            ),
                            default_repr=None,
                        ),
                        ParameterIR(
                            name="optional_filter",
                            kind=1,
                            annotation_ir=OptionalTypeIR(inner=IdentityTypeIR(signature_text="str")),
                            default_repr="None",
                        ),
                    ),
                    is_async_gen=False,
                    is_async=True,
                    return_transformer_ir=AwaitableTypeIR(inner=ListTypeIR(item=IdentityTypeIR(signature_text="str"))),
                ),
            ),
        ),
    ),
    module_functions_ir=(),
)

REG_TWO_MOD = SyncRegistry(
    {
        ImplQualifiedRef(IMPL, "EmitModuleClassA"): (TARGET, "TestClass"),
        ImplQualifiedRef(IMPL, "EmitModuleClassB"): (TARGET, "ComplexClass"),
    }
)


def test_emit_module_two_classes_separated_by_blank_lines():
    generated_code = SyncAsyncWrapperEmitter().emit_module(IR_MODULE_TWO_CLASSES, REG_TWO_MOD)
    compile(generated_code, "<string>", "exec")

    class_pattern = r"^class\s+\w+"
    lines = generated_code.split("\n")
    class_line_indices = [i for i, line in enumerate(lines) if re.match(class_pattern, line.strip())]
    assert len(class_line_indices) >= 2, "Should have at least 2 classes"
    for idx in class_line_indices[1:]:
        prev_line_idx = idx - 1
        assert prev_line_idx >= 0
        assert lines[prev_line_idx].strip() == ""
    assert (
        "_synchronizer.register_wrapper_class(test.unit.compile.test_emit_module.EmitModuleClassA, EmitModuleClassA)"
        in generated_code
    )
    assert (
        "_synchronizer.register_wrapper_class(test.unit.compile.test_emit_module.EmitModuleClassB, EmitModuleClassB)"
        in generated_code
    )
