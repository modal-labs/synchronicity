"""Unit tests for IR → emitted source (wrapper classes).

IR literals are explicit dataclasses in this module (same shapes as the parse layer).
``IMPL`` is this module so emitted implementation references match assertions.
"""

from __future__ import annotations

from synchronicity.codegen.emitters.sync_async_wrappers import emit_class_from_ir
from synchronicity.codegen.ir import ClassWrapperIR, MethodBindingKind, MethodWrapperIR, ParameterIR, SignatureIR
from synchronicity.codegen.transformer_ir import (
    AsyncGeneratorTypeIR,
    AsyncIteratorTypeIR,
    AwaitableTypeIR,
    CoroutineTypeIR,
    DictTypeIR,
    IdentityTypeIR,
    ImplQualifiedRef,
    ListTypeIR,
    OptionalTypeIR,
    SelfTypeIR,
    WrappedClassTypeIR,
    WrapperRef,
)

IMPL = __name__
TARGET = "test_module"

IR_CLASS_AITER_ASYNC_GEN = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitAsyncWithGenerator"),
    wrapper_ref=WrapperRef(TARGET, "EmitAsyncWithGenerator"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="__aiter__",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=True,
            is_async=True,
            return_transformer_ir=AsyncGeneratorTypeIR(
                yield_item=IdentityTypeIR(signature_text="float"), send_type_str="None"
            ),
        ),
    ),
)

IR_CLASS_AITER_ASYNC_ITER_TYPE = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitAsyncIterType"),
    wrapper_ref=WrapperRef(TARGET, "EmitAsyncIterType"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="__aiter__",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=False,
            is_async=False,
            return_transformer_ir=AsyncIteratorTypeIR(item=IdentityTypeIR(signature_text="bool")),
        ),
    ),
)

IR_CLASS_AITER_ASYNC_NO_ANN = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitAsyncWithoutAnnotation"),
    wrapper_ref=WrapperRef(TARGET, "EmitAsyncWithoutAnnotation"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="__aiter__",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="typing.Any")),
        ),
    ),
)

IR_CLASS_AITER_ASYNC_WITH_ANN = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitAsyncWithAnnotation"),
    wrapper_ref=WrapperRef(TARGET, "EmitAsyncWithAnnotation"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="__aiter__",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=AsyncIteratorTypeIR(item=IdentityTypeIR(signature_text="int"))),
        ),
    ),
)

IR_CLASS_AITER_SYNC_NO_ANN = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitSyncWithoutAnnotation"),
    wrapper_ref=WrapperRef(TARGET, "EmitSyncWithoutAnnotation"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="__aiter__",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=False,
            is_async=False,
            return_transformer_ir=IdentityTypeIR(signature_text=""),
        ),
    ),
)

IR_CLASS_AITER_SYNC_WITH_ANN = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitSyncWithAnnotation"),
    wrapper_ref=WrapperRef(TARGET, "EmitSyncWithAnnotation"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="__aiter__",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=False,
            is_async=False,
            return_transformer_ir=AsyncIteratorTypeIR(item=IdentityTypeIR(signature_text="str")),
        ),
    ),
)

IR_CLASS_ASYNC_GEN = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitAsyncGeneratorClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitAsyncGeneratorClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="__init__",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(
                    name="items",
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
            method_name="stream_items",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=True,
            is_async=True,
            return_transformer_ir=AsyncGeneratorTypeIR(
                yield_item=IdentityTypeIR(signature_text="str"), send_type_str="None"
            ),
        ),
        MethodWrapperIR(
            method_name="stream_with_filter",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(
                    name="prefix", kind=1, annotation_ir=IdentityTypeIR(signature_text="str"), default_repr=None
                ),
            ),
            is_async_gen=True,
            is_async=True,
            return_transformer_ir=AsyncGeneratorTypeIR(
                yield_item=IdentityTypeIR(signature_text="str"), send_type_str="None"
            ),
        ),
    ),
)

IR_CLASS_ASYNC_ITERABLE = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitAsyncIterableClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitAsyncIterableClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="__aiter__",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=False,
            is_async=False,
            return_transformer_ir=AsyncIteratorTypeIR(item=IdentityTypeIR(signature_text="str")),
        ),
    ),
)

IR_CLASS_ASYNC_ITERATOR = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitAsyncIteratorClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitAsyncIteratorClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="__aiter__",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=False,
            is_async=False,
            return_transformer_ir=SelfTypeIR(
                owner_impl=ImplQualifiedRef(IMPL, "EmitAsyncIteratorClass"),
                wrapper=WrapperRef(TARGET, "EmitAsyncIteratorClass"),
            ),
        ),
        MethodWrapperIR(
            method_name="__anext__",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="int")),
        ),
    ),
)

IR_CLASS_AWAITABLE_METHOD = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitAwaitableMethodClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitAwaitableMethodClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="create_awaitable",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(name="x", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="str")),
        ),
    ),
)
IR_CLASS_OVERLOADED_METHOD = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitOverloadedMethodClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitOverloadedMethodClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="resolve",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(ParameterIR(name="value", kind=1, annotation_ir=None, default_repr=None),),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="typing.Any")),
            overloads=(
                SignatureIR(
                    parameters=(
                        ParameterIR(
                            name="value",
                            kind=1,
                            annotation_ir=IdentityTypeIR(signature_text="int"),
                            default_repr=None,
                        ),
                    ),
                    return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="int")),
                ),
                SignatureIR(
                    parameters=(
                        ParameterIR(
                            name="value",
                            kind=1,
                            annotation_ir=WrappedClassTypeIR(
                                impl=ImplQualifiedRef(IMPL, "Node"),
                                wrapper=WrapperRef(TARGET, "Node"),
                            ),
                            default_repr=None,
                        ),
                    ),
                    return_transformer_ir=AwaitableTypeIR(
                        inner=WrappedClassTypeIR(
                            impl=ImplQualifiedRef(IMPL, "Node"),
                            wrapper=WrapperRef(TARGET, "Node"),
                        )
                    ),
                ),
            ),
        ),
    ),
)

IR_CLASS_COMPLEX = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitComplexClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitComplexClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
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
            method_name="get_data_length",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="int")),
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
)

IR_CLASS_CONTAINER = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitContainer"),
    wrapper_ref=WrapperRef(TARGET, "EmitContainer"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="__init__",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(
                    name="node",
                    kind=1,
                    annotation_ir=WrappedClassTypeIR(
                        impl=ImplQualifiedRef(IMPL, "EmitNode"), wrapper=WrapperRef(TARGET, "Node")
                    ),
                    default_repr=None,
                ),
                ParameterIR(name="name", kind=1, annotation_ir=IdentityTypeIR(signature_text="str"), default_repr=None),
                ParameterIR(name="count", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr="5"),
            ),
            is_async_gen=False,
            is_async=False,
            return_transformer_ir=IdentityTypeIR(signature_text=""),
        ),
    ),
)

IR_CLASS_COROUTINE_METHOD = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitCoroutineMethodClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitCoroutineMethodClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="create_coroutine",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(name="x", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=CoroutineTypeIR(return_type=IdentityTypeIR(signature_text="str")),
        ),
    ),
)

IR_CLASS_EMPTY = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitEmptyClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitEmptyClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
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
            method_name="sync_method",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=False,
            is_async=False,
            return_transformer_ir=IdentityTypeIR(signature_text="int"),
        ),
    ),
)

IR_CLASS_MIXED = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitMixedClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitMixedClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
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
            method_name="process_generator",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=True,
            is_async=True,
            return_transformer_ir=AsyncGeneratorTypeIR(
                yield_item=IdentityTypeIR(signature_text="str"), send_type_str="None"
            ),
        ),
        MethodWrapperIR(
            method_name="process_sync",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(name="item", kind=1, annotation_ir=IdentityTypeIR(signature_text="str"), default_repr=None),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="str")),
        ),
        MethodWrapperIR(
            method_name="sync_method",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(name="item", kind=1, annotation_ir=IdentityTypeIR(signature_text="str"), default_repr=None),
            ),
            is_async_gen=False,
            is_async=False,
            return_transformer_ir=IdentityTypeIR(signature_text="str"),
        ),
    ),
)

IR_CLASS_NO_INIT = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitNoInit"),
    wrapper_ref=WrapperRef(TARGET, "EmitNoInit"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="method",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="int")),
        ),
    ),
)

IR_CLASS_SELF = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitSelfMethodClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitSelfMethodClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="accept",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(
                    name="s",
                    kind=1,
                    annotation_ir=SelfTypeIR(
                        owner_impl=ImplQualifiedRef(IMPL, "EmitSelfMethodClass"),
                        wrapper=WrapperRef(TARGET, "EmitSelfMethodClass"),
                    ),
                    default_repr=None,
                ),
            ),
            is_async_gen=False,
            is_async=False,
            return_transformer_ir=SelfTypeIR(
                owner_impl=ImplQualifiedRef(IMPL, "EmitSelfMethodClass"),
                wrapper=WrapperRef(TARGET, "EmitSelfMethodClass"),
            ),
        ),
    ),
)

IR_CLASS_SIMPLE = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitSimpleClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitSimpleClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
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
            method_name="add_to_value",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(
                    name="amount", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None
                ),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="int")),
        ),
        MethodWrapperIR(
            method_name="get_value",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="int")),
        ),
        MethodWrapperIR(
            method_name="set_value",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(
                    name="new_value", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None
                ),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="None")),
        ),
    ),
)

IR_CLASS_VARARGS = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitVarArgsClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitVarArgsClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="method_with_posonly",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(name="x", kind=0, annotation_ir=None, default_repr=None),
                ParameterIR(name="y", kind=0, annotation_ir=None, default_repr=None),
                ParameterIR(name="z", kind=1, annotation_ir=None, default_repr=None),
                ParameterIR(name="w", kind=1, annotation_ir=None, default_repr="10"),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="int")),
        ),
        MethodWrapperIR(
            method_name="method_with_varargs",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(name="a", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),
                ParameterIR(name="args", kind=2, annotation_ir=IdentityTypeIR(signature_text="str"), default_repr=None),
                ParameterIR(name="b", kind=3, annotation_ir=None, default_repr=None),
                ParameterIR(
                    name="kwargs", kind=4, annotation_ir=IdentityTypeIR(signature_text="float"), default_repr=None
                ),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="str")),
        ),
    ),
)


def _impl_short(ir: ClassWrapperIR) -> str:
    return ir.impl_ref.qualname.rpartition(".")[2]


def test_emit_class_basic():
    ir = IR_CLASS_SIMPLE
    code = emit_class_from_ir(ir, TARGET)
    compile(code, "<string>", "exec")
    assert f"class {_impl_short(ir)}:" in code
    assert "_impl_instance" in code
    assert "@wrapped_method(" in code
    assert "def get_value(self" in code
    assert "def set_value(self" in code
    assert "def add_to_value(self" in code
    assert "impl_method = " in code


def test_emit_class_method_descriptors():
    code = emit_class_from_ir(IR_CLASS_SIMPLE, TARGET)
    assert "MethodSurface" not in code
    assert "@wrapped_method(__add_to_value_aio)" in code
    assert "async def __add_to_value_aio(self, amount: int) -> int" in code
    assert "def add_to_value(self, amount: int) -> int" in code


def test_emit_class_complex_types():
    code = emit_class_from_ir(IR_CLASS_COMPLEX, TARGET)
    compile(code, "<string>", "exec")
    assert "config: dict[str, int]" in code
    assert (
        "optional_filter: typing.Union[str, None]" in code
        or "optional_filter: str | None" in code
        or "optional_filter: typing.Optional[str]" in code
    )
    assert "-> list[str]" in code


def test_emit_class_async_generators():
    code = emit_class_from_ir(IR_CLASS_ASYNC_GEN, TARGET)
    compile(code, "<string>", "exec")
    assert "_run_generator_sync" in code
    assert "_run_generator_async" in code
    assert "_sent = yield _item" in code
    assert "await _wrapped.asend(_sent)" in code
    # No helper functions needed when yield type doesn't need translation
    assert "@staticmethod" not in code
    assert "_wrap_async_gen" not in code


def test_emit_class_mixed_methods():
    code = emit_class_from_ir(IR_CLASS_MIXED, TARGET)
    compile(code, "<string>", "exec")
    assert "@wrapped_method(" in code
    assert "def process_sync(self" in code
    assert "def process_generator(self" in code


def test_emit_class_type_annotations_preserved():
    code = emit_class_from_ir(IR_CLASS_SIMPLE, TARGET)
    assert "new_value: int" in code
    assert "amount: int" in code
    assert "-> int" in code
    assert "-> None" in code


def test_emit_class_impl_instance_access():
    ir = IR_CLASS_SIMPLE
    code = emit_class_from_ir(ir, TARGET)
    short = _impl_short(ir)
    assert f"self._impl_instance = {IMPL}.{short}(" in code
    assert f"class {short}:" in code
    assert "_synchronizer._run_function_async" in code


def test_emit_class_multiple_wrapped_registry_entries():
    for ir in (IR_CLASS_SIMPLE, IR_CLASS_COMPLEX):
        code = emit_class_from_ir(ir, TARGET)
        compile(code, "<string>", "exec")
        assert f"class {_impl_short(ir)}:" in code
        assert "_impl_instance" in code


def test_emit_class_no_async_methods():
    ir = IR_CLASS_EMPTY
    code = emit_class_from_ir(ir, TARGET)
    compile(code, "<string>", "exec")
    assert f"class {_impl_short(ir)}:" in code
    assert "_impl_instance" in code


def test_emit_class_method_with_varargs():
    code = emit_class_from_ir(IR_CLASS_VARARGS, TARGET)
    assert "*args: str" in code
    assert "**kwargs: float" in code
    assert "a: int, *args: str, b, **kwargs: float" in code
    assert "x, y, /" in code
    assert "*args" in code
    assert "b=b" in code
    assert "**kwargs" in code
    assert "impl_method(self._impl_instance, a, *args, b=b, **kwargs)" in code


def test_emit_class_constructor_with_wrapped_param():
    code = emit_class_from_ir(IR_CLASS_CONTAINER, TARGET)
    compile(code, "<string>", "exec")
    assert 'def __init__(self, node: "Node", name: str, count: int = 5):' in code
    assert "node_impl = node._impl_instance" in code
    assert f"self._impl_instance = {IMPL}.EmitContainer(node_impl, name, count)" in code
    assert "name_impl" not in code
    assert "count_impl" not in code


def test_emit_class_sync_method_returning_coroutine():
    code = emit_class_from_ir(IR_CLASS_COROUTINE_METHOD, TARGET)
    assert "MethodSurface" not in code
    assert "@wrapped_method(__create_coroutine_aio)" in code
    assert "def create_coroutine(self, x: int) -> str:" in code
    assert "async def __create_coroutine_aio(self, x: int) -> str:" in code
    assert "_run_function_sync" in code
    assert "_run_function_async" in code


def test_emit_class_sync_method_returning_awaitable():
    code = emit_class_from_ir(IR_CLASS_AWAITABLE_METHOD, TARGET)
    assert "MethodSurface" not in code
    assert "@wrapped_method(__create_awaitable_aio)" in code
    assert "def create_awaitable(self, x: int) -> str:" in code
    assert "async def __create_awaitable_aio(self, x: int) -> str:" in code
    assert "_run_function_sync" in code
    assert "_run_function_async" in code


def test_emit_class_method_overloads_translate_each_overload():
    code = emit_class_from_ir(IR_CLASS_OVERLOADED_METHOD, TARGET)
    compile(code, "<string>", "exec")
    assert "class _EmitOverloadedMethodClass_resolve_MethodSurface(typing.Protocol):" in code
    assert "def __call__(self, value: int) -> int: ..." in code
    assert 'def __call__(self, value: "Node") -> "Node": ...' in code
    assert "def aio(self, value: int) -> typing.Coroutine[typing.Any, typing.Any, int]: ..." in code
    assert 'def aio(self, value: "Node") -> typing.Coroutine[typing.Any, typing.Any, "Node"]: ...' in code
    assert (
        "@wrapped_overloaded_method(__resolve_aio, " "surface_type=_EmitOverloadedMethodClass_resolve_MethodSurface)"
    ) in code
    assert "async def __resolve_aio(self, value) -> typing.Any:" in code
    assert "def resolve(self, value) -> typing.Any:" in code


def test_emit_class_aiter_typed_iter():
    code = emit_class_from_ir(IR_CLASS_ASYNC_ITERABLE, TARGET)
    assert 'def __iter__(self) -> "synchronicity.types.SyncOrAsyncIterator[str]":' in code
    assert 'def __aiter__(self) -> "synchronicity.types.SyncOrAsyncIterator[str]":' in code


def test_emit_class_anext_typed_next():
    code = emit_class_from_ir(IR_CLASS_ASYNC_ITERATOR, TARGET)
    assert "def __next__(self) -> int:" in code
    assert "async def __anext__(self) -> int:" in code
    assert 'def __iter__(self) -> "typing.Self":' in code
    assert 'def __aiter__(self) -> "typing.Self":' in code


def test_emit_class_preserves_typing_self():
    code = emit_class_from_ir(IR_CLASS_SELF, TARGET)
    assert 'def accept(self, s: typing.Self) -> "typing.Self":' in code
    assert "typing.cast(typing.Self, self._from_impl(result))" in code
    assert "s_impl = s._impl_instance" in code


def test_emit_class_aiter_signature_variations():
    code = emit_class_from_ir(IR_CLASS_AITER_SYNC_WITH_ANN, TARGET)
    assert 'def __iter__(self) -> "synchronicity.types.SyncOrAsyncIterator[str]":' in code
    assert 'def __aiter__(self) -> "synchronicity.types.SyncOrAsyncIterator[str]":' in code

    code = emit_class_from_ir(IR_CLASS_AITER_SYNC_NO_ANN, TARGET)
    assert "def __iter__(self):" in code
    assert "def __aiter__(self):" in code
    assert " -> :" not in code

    code = emit_class_from_ir(IR_CLASS_AITER_ASYNC_WITH_ANN, TARGET)
    assert 'def __iter__(self) -> "synchronicity.types.SyncOrAsyncIterator[int]":' in code
    assert 'def __aiter__(self) -> "synchronicity.types.SyncOrAsyncIterator[int]":' in code

    code = emit_class_from_ir(IR_CLASS_AITER_ASYNC_NO_ANN, TARGET)
    assert "def __iter__(self) -> typing.Any:" in code
    assert "def __aiter__(self) -> typing.Any:" in code

    code = emit_class_from_ir(IR_CLASS_AITER_ASYNC_GEN, TARGET)
    assert 'def __iter__(self) -> "typing.Generator[float, None, None]":' in code
    assert 'def __aiter__(self) -> "typing.AsyncGenerator[float, None]":' in code

    code = emit_class_from_ir(IR_CLASS_AITER_ASYNC_ITER_TYPE, TARGET)
    assert 'def __iter__(self) -> "synchronicity.types.SyncOrAsyncIterator[bool]":' in code
    assert 'def __aiter__(self) -> "synchronicity.types.SyncOrAsyncIterator[bool]":' in code


def test_emit_class_without_explicit_init():
    ir = IR_CLASS_NO_INIT
    code = emit_class_from_ir(ir, TARGET)
    assert "def __init__(self):" in code
    assert "def __init__(self, *args, **kwargs):" not in code
    assert f"{IMPL}.{_impl_short(ir)}()" in code
