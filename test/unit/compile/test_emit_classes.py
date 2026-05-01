"""Unit tests for IR → emitted source (wrapper classes).

IR literals are explicit dataclasses in this module (same shapes as the parse layer).
``IMPL`` is this module so emitted implementation references match assertions.
"""

from __future__ import annotations

import dataclasses
import weakref

from synchronicity2.codegen.emitters.sync_async_wrappers import emit_class_from_ir
from synchronicity2.codegen.ir import (
    ClassPropertyWrapperIR,
    ClassWrapperIR,
    MethodBindingKind,
    MethodWrapperIR,
    ParameterIR,
    SignatureIR,
)
from synchronicity2.codegen.transformer_ir import (
    AsyncContextManagerTypeIR,
    AsyncGeneratorTypeIR,
    AsyncIteratorTypeIR,
    AwaitableTypeIR,
    CallableTypeIR,
    CollectionTypeIR,
    CoroutineTypeIR,
    DictTypeIR,
    IdentityTypeIR,
    ImplQualifiedRef,
    ListTypeIR,
    OptionalTypeIR,
    SelfTypeIR,
    SequenceTypeIR,
    SubscriptedWrappedClassTypeIR,
    TypeVarIR,
    UnionTypeIR,
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
                    default_expr=None,
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
                    name="prefix", kind=1, annotation_ir=IdentityTypeIR(signature_text="str"), default_expr=None
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
IR_CLASS_METHOD_WITH_DEFAULTS = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitMethodDefaults"),
    wrapper_ref=WrapperRef(TARGET, "EmitMethodDefaults"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="configure",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(
                    name="name",
                    kind=1,
                    annotation_ir=IdentityTypeIR(signature_text="str"),
                    default_expr="'hello'",
                ),
                ParameterIR(
                    name="enabled",
                    kind=1,
                    annotation_ir=IdentityTypeIR(signature_text="bool"),
                    default_expr="True",
                ),
                ParameterIR(
                    name="payload",
                    kind=1,
                    annotation_ir=IdentityTypeIR(signature_text="bytes"),
                    default_expr="b'data'",
                ),
            ),
            is_async_gen=False,
            is_async=False,
            return_transformer_ir=IdentityTypeIR(signature_text="str"),
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
                ParameterIR(name="x", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_expr=None),
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
            parameters=(ParameterIR(name="value", kind=1, annotation_ir=None, default_expr=None),),
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
                            default_expr=None,
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
                            default_expr=None,
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

IR_CLASS_SYNC_OVERLOADED_METHOD = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitSyncOverloadedMethodClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitSyncOverloadedMethodClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="decorate",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(ParameterIR(name="value", kind=1, annotation_ir=None, default_expr=None),),
            is_async_gen=False,
            is_async=False,
            return_transformer_ir=IdentityTypeIR(signature_text="typing.Any"),
            overloads=(
                SignatureIR(
                    parameters=(
                        ParameterIR(
                            name="value",
                            kind=1,
                            annotation_ir=IdentityTypeIR(signature_text="int"),
                            default_expr=None,
                        ),
                    ),
                    return_transformer_ir=IdentityTypeIR(signature_text="int"),
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
                            default_expr=None,
                        ),
                    ),
                    return_transformer_ir=WrappedClassTypeIR(
                        impl=ImplQualifiedRef(IMPL, "Node"),
                        wrapper=WrapperRef(TARGET, "Node"),
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
                    default_expr=None,
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
                    default_expr=None,
                ),
                ParameterIR(
                    name="optional_filter",
                    kind=1,
                    annotation_ir=OptionalTypeIR(inner=IdentityTypeIR(signature_text="str")),
                    default_expr="None",
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
                    default_expr=None,
                ),
                ParameterIR(name="name", kind=1, annotation_ir=IdentityTypeIR(signature_text="str"), default_expr=None),
                ParameterIR(name="count", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_expr="5"),
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
                ParameterIR(name="x", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_expr=None),
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
                    name="value", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_expr=None
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
                    default_expr=None,
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
                ParameterIR(name="item", kind=1, annotation_ir=IdentityTypeIR(signature_text="str"), default_expr=None),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="str")),
        ),
        MethodWrapperIR(
            method_name="sync_method",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(name="item", kind=1, annotation_ir=IdentityTypeIR(signature_text="str"), default_expr=None),
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
                    default_expr=None,
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

IR_CLASS_CLASSMETHOD_SELF = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitSelfClassmethodClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitSelfClassmethodClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="create",
            method_type=MethodBindingKind.CLASSMETHOD,
            parameters=(),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(
                inner=SelfTypeIR(
                    owner_impl=ImplQualifiedRef(IMPL, "EmitSelfClassmethodClass"),
                    wrapper=WrapperRef(TARGET, "EmitSelfClassmethodClass"),
                )
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
                    name="value", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_expr=None
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
                    name="amount", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_expr=None
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
                    name="new_value", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_expr=None
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
                ParameterIR(name="x", kind=0, annotation_ir=None, default_expr=None),
                ParameterIR(name="y", kind=0, annotation_ir=None, default_expr=None),
                ParameterIR(name="z", kind=1, annotation_ir=None, default_expr=None),
                ParameterIR(name="w", kind=1, annotation_ir=None, default_expr="10"),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="int")),
        ),
        MethodWrapperIR(
            method_name="method_with_varargs",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(name="a", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_expr=None),
                ParameterIR(name="args", kind=2, annotation_ir=IdentityTypeIR(signature_text="str"), default_expr=None),
                ParameterIR(name="b", kind=3, annotation_ir=None, default_expr=None),
                ParameterIR(
                    name="kwargs", kind=4, annotation_ir=IdentityTypeIR(signature_text="float"), default_expr=None
                ),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="str")),
        ),
    ),
)

IR_CLASS_TRANSLATED_STATICMETHOD_VARARGS = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitTranslatedStaticVarArgsClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitTranslatedStaticVarArgsClass"),
    wrapped_bases=(),
    generic_type_parameters=None,
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="collect",
            method_type=MethodBindingKind.STATICMETHOD,
            parameters=(
                ParameterIR(
                    name="args",
                    kind=2,
                    annotation_ir=WrappedClassTypeIR(
                        impl=ImplQualifiedRef(IMPL, "Node"),
                        wrapper=WrapperRef(TARGET, "Node"),
                    ),
                    default_expr=None,
                ),
                ParameterIR(
                    name="kwargs",
                    kind=4,
                    annotation_ir=WrappedClassTypeIR(
                        impl=ImplQualifiedRef(IMPL, "Node"),
                        wrapper=WrapperRef(TARGET, "Node"),
                    ),
                    default_expr=None,
                ),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="list[str]")),
        ),
    ),
)

IR_CLASS_TRANSLATED_STATICMETHOD_SUBSCRIPTED_VARARGS = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "EmitTranslatedSubscriptedStaticVarArgsClass"),
    wrapper_ref=WrapperRef(TARGET, "EmitTranslatedSubscriptedStaticVarArgsClass"),
    wrapped_bases=(),
    generic_type_parameters=("T",),
    attributes=(),
    properties=(),
    methods=(
        MethodWrapperIR(
            method_name="collect",
            method_type=MethodBindingKind.STATICMETHOD,
            parameters=(
                ParameterIR(
                    name="args",
                    kind=2,
                    annotation_ir=SubscriptedWrappedClassTypeIR(
                        impl=ImplQualifiedRef(IMPL, "Node"),
                        wrapper=WrapperRef(TARGET, "Node"),
                        type_args=(IdentityTypeIR(signature_text="T"),),
                    ),
                    default_expr=None,
                ),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="list[str]")),
        ),
    ),
)


def _impl_short(ir: ClassWrapperIR) -> str:
    return ir.impl_ref.qualname.rpartition(".")[2]


def test_emit_class_basic():
    ir = IR_CLASS_SIMPLE
    code = emit_class_from_ir(ir, TARGET)
    compile(code, "<string>", "exec")
    assert f"# Proxy type for the underlying implementation type {IMPL}.{_impl_short(ir)}." in code
    assert f"class {_impl_short(ir)}:" in code
    assert "_impl_instance" in code
    assert "@method_with_aio(" in code
    assert "def get_value(self" in code
    assert "def set_value(self" in code
    assert "def add_to_value(self" in code
    assert f"{IMPL}.EmitSimpleClass.add_to_value(self._impl_instance, amount)" in code


def test_emit_class_method_descriptors():
    code = emit_class_from_ir(IR_CLASS_SIMPLE, TARGET)
    assert "class _EmitSimpleClass_add_to_value_MethodWithAio(MethodWithAio):" in code
    assert "@method_with_aio(_EmitSimpleClass_add_to_value_MethodWithAio)" in code
    assert "async def aio(self, amount: int) -> int:" in code
    assert "def add_to_value(self, amount: int) -> int" in code
    assert "return self._sync_impl(amount)" in code
    assert "self._with_aio_from_impl = _from_impl" not in code
    assert "def _from_impl(self, impl_instance: typing.Any) -> typing.Any:" not in code
    assert "impl_method =" not in code


def test_emit_class_method_docstring_skips_with_aio_class_level_copy():
    method_ir = dataclasses.replace(IR_CLASS_AWAITABLE_METHOD.methods[0], docstring="Method docstring.")
    ir = dataclasses.replace(IR_CLASS_AWAITABLE_METHOD, methods=(method_ir,))
    code = emit_class_from_ir(ir, TARGET)
    assert code.count('"""Method docstring."""') == 3
    assert (
        "class _EmitAwaitableMethodClass_create_awaitable_MethodWithAio(MethodWithAio):\n" '    """Method docstring."""'
    ) not in code


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


def test_emit_class_quotes_annotations_shadowed_by_class_namespace():
    ir = ClassWrapperIR(
        impl_ref=ImplQualifiedRef(IMPL, "EmitShadowedBuiltinAnnotation"),
        wrapper_ref=WrapperRef(TARGET, "EmitShadowedBuiltinAnnotation"),
        wrapped_bases=(),
        generic_type_parameters=None,
        attributes=(),
        properties=(),
        methods=(
            MethodWrapperIR(
                method_name="list",
                method_type=MethodBindingKind.INSTANCE,
                parameters=(),
                is_async_gen=False,
                is_async=False,
                return_transformer_ir=ListTypeIR(item=IdentityTypeIR(signature_text="str")),
            ),
            MethodWrapperIR(
                method_name="ls",
                method_type=MethodBindingKind.INSTANCE,
                parameters=(),
                is_async_gen=False,
                is_async=False,
                return_transformer_ir=ListTypeIR(item=IdentityTypeIR(signature_text="str")),
            ),
        ),
    )

    code = emit_class_from_ir(ir, TARGET)

    assert 'def ls(self) -> "list[str]":' in code
    exec(code, {"weakref": weakref})


def test_emit_class_async_generators():
    code = emit_class_from_ir(IR_CLASS_ASYNC_GEN, TARGET)
    compile(code, "<string>", "exec")
    assert "_run_generator_sync" in code
    assert "_run_generator_async" in code
    assert "_sent = yield _item" in code
    assert "await _wrapped.asend(_sent)" in code
    assert "impl_method =" not in code
    # No helper functions needed when yield type doesn't need translation
    assert "@staticmethod" not in code
    assert "_wrap_async_gen" not in code


def test_emit_class_mixed_methods():
    code = emit_class_from_ir(IR_CLASS_MIXED, TARGET)
    compile(code, "<string>", "exec")
    assert "@method_with_aio(" in code
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
    assert f"{IMPL}.EmitVarArgsClass.method_with_varargs(self._impl_instance, a, *args, b=b, **kwargs)" in code


def test_emit_staticmethod_translated_varargs_and_kwargs():
    code = emit_class_from_ir(IR_CLASS_TRANSLATED_STATICMETHOD_VARARGS, TARGET)

    assert 'def collect(*args: "Node", **kwargs: "Node") -> list[str]:' in code
    assert "args_impl = tuple(_item._impl_instance for _item in args)" in code
    assert "kwargs_impl = {_key: _value._impl_instance for _key, _value in kwargs.items()}" in code
    assert f"{IMPL}.EmitTranslatedStaticVarArgsClass.collect(*args_impl, **kwargs_impl)" in code


def test_emit_staticmethod_translated_subscripted_varargs_quotes_forward_ref():
    code = emit_class_from_ir(IR_CLASS_TRANSLATED_STATICMETHOD_SUBSCRIPTED_VARARGS, TARGET)

    assert 'def __call__(self, *args: "Node[T]") -> list[str]:' in code
    assert 'def aio(self, *args: "Node[T]") -> list[str]:' in code
    assert 'def collect(*args: "Node[T]") -> list[str]:' in code
    assert "args_impl = tuple(_item._impl_instance for _item in args)" in code


def test_emit_staticmethod_with_method_local_typevar_without_type_checking_stub():
    ir = ClassWrapperIR(
        impl_ref=ImplQualifiedRef(IMPL, "EmitMethodLocalTypeVarClass"),
        wrapper_ref=WrapperRef(TARGET, "EmitMethodLocalTypeVarClass"),
        wrapped_bases=(),
        generic_type_parameters=None,
        attributes=(),
        properties=(),
        class_properties=(),
        manual_attributes=(),
        methods=(
            MethodWrapperIR(
                method_name="echo",
                method_type=MethodBindingKind.STATICMETHOD,
                parameters=(
                    ParameterIR(
                        name="value",
                        kind=1,
                        annotation_ir=TypeVarIR(name="T"),
                        default_expr=None,
                    ),
                ),
                is_async_gen=False,
                is_async=True,
                return_transformer_ir=AwaitableTypeIR(inner=TypeVarIR(name="T")),
            ),
        ),
    )

    code = emit_class_from_ir(ir, TARGET)

    assert "@staticmethod_with_aio(_EmitMethodLocalTypeVarClass_echo_MethodWithAio)" in code
    assert "if typing.TYPE_CHECKING" not in code


def test_emit_class_method_various_builtin_default_values():
    code = emit_class_from_ir(IR_CLASS_METHOD_WITH_DEFAULTS, TARGET)
    compile(code, "<string>", "exec")
    assert "def configure(self, name: str = 'hello', enabled: bool = True, payload: bytes = b'data') -> str:" in code


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
    assert "class _EmitCoroutineMethodClass_create_coroutine_MethodWithAio(MethodWithAio):" in code
    assert "@method_with_aio(_EmitCoroutineMethodClass_create_coroutine_MethodWithAio)" in code
    assert "def create_coroutine(self, x: int) -> str:" in code
    assert "async def aio(self, x: int) -> str:" in code
    assert "_run_function_sync" in code
    assert "_run_function_async" in code


def test_emit_class_sync_method_returning_awaitable():
    code = emit_class_from_ir(IR_CLASS_AWAITABLE_METHOD, TARGET)
    assert "class _EmitAwaitableMethodClass_create_awaitable_MethodWithAio(MethodWithAio):" in code
    assert "@method_with_aio(_EmitAwaitableMethodClass_create_awaitable_MethodWithAio)" in code
    assert "def create_awaitable(self, x: int) -> str:" in code
    assert "async def aio(self, x: int) -> str:" in code
    assert "_run_function_sync" in code
    assert "_run_function_async" in code


def test_emit_class_method_overloads_translate_each_overload():
    code = emit_class_from_ir(IR_CLASS_OVERLOADED_METHOD, TARGET)
    compile(code, "<string>", "exec")
    assert "class _EmitOverloadedMethodClass_resolve_MethodWithAio(MethodWithAio):" in code
    assert "def __call__(self, value: int) -> int: ..." in code
    assert 'def __call__(self, value: "Node") -> "Node": ...' in code
    assert "async def aio(self, value: int) -> int: ..." in code
    assert 'async def aio(self, value: "Node") -> "Node": ...' in code
    assert "def __call__(self, value) -> typing.Any:" in code
    assert "return self._sync_impl(value)" in code
    assert "async def aio(self, value) -> typing.Any:" in code
    assert "@method_with_aio(_EmitOverloadedMethodClass_resolve_MethodWithAio)" in code
    assert (
        "_run_function_async("
        "test.unit.compile.test_emit_classes.EmitOverloadedMethodClass.resolve("
        "self._wrapper_instance._impl_instance, value))" in code
    )
    assert "def resolve(self, value) -> typing.Any:" in code


def test_emit_sync_method_overloads():
    code = emit_class_from_ir(IR_CLASS_SYNC_OVERLOADED_METHOD, TARGET)
    compile(code, "<string>", "exec")
    assert "@typing.overload" in code
    assert "def decorate(self, value: int) -> int: ..." in code
    assert 'def decorate(self, value: "Node") -> "Node": ...' in code
    assert "def decorate(self, value) -> typing.Any:" in code


def test_emit_class_aiter_typed_iter():
    code = emit_class_from_ir(IR_CLASS_ASYNC_ITERABLE, TARGET)
    assert "def __iter__(self) -> synchronicity2.types.SyncOrAsyncIterator[str]:" in code
    assert "def __aiter__(self) -> synchronicity2.types.SyncOrAsyncIterator[str]:" in code


def test_emit_class_anext_typed_next():
    code = emit_class_from_ir(IR_CLASS_ASYNC_ITERATOR, TARGET)
    assert "def __next__(self) -> int:" in code
    assert "async def __anext__(self) -> int:" in code
    assert "def __iter__(self) -> typing.Self:" in code
    assert "def __aiter__(self) -> typing.Self:" in code


def test_emit_class_preserves_typing_self():
    code = emit_class_from_ir(IR_CLASS_SELF, TARGET)
    assert "def accept(self, s: typing.Self) -> typing.Self:" in code
    assert "typing.cast(typing.Self, self._from_impl(result))" in code
    assert "s_impl = s._impl_instance" in code


def test_emit_classmethod_with_aio_threads_owner_self_type_into_helper():
    code = emit_class_from_ir(IR_CLASS_CLASSMETHOD_SELF, TARGET)
    assert (
        "_EmitSelfClassmethodClass_create_SelfType = typing.TypeVar("
        '"_EmitSelfClassmethodClass_create_SelfType", bound="EmitSelfClassmethodClass")'
    ) in code
    assert (
        "class _EmitSelfClassmethodClass_create_MethodWithAio(MethodWithAio, "
        "typing.Generic[_EmitSelfClassmethodClass_create_SelfType]):"
    ) in code
    assert "def __call__(self) -> _EmitSelfClassmethodClass_create_SelfType:" in code
    assert "async def aio(self) -> _EmitSelfClassmethodClass_create_SelfType:" in code


def test_emit_class_aiter_signature_variations():
    code = emit_class_from_ir(IR_CLASS_AITER_SYNC_WITH_ANN, TARGET)
    assert "def __iter__(self) -> synchronicity2.types.SyncOrAsyncIterator[str]:" in code
    assert "def __aiter__(self) -> synchronicity2.types.SyncOrAsyncIterator[str]:" in code

    code = emit_class_from_ir(IR_CLASS_AITER_SYNC_NO_ANN, TARGET)
    assert "def __iter__(self):" in code
    assert "def __aiter__(self):" in code
    assert " -> :" not in code

    code = emit_class_from_ir(IR_CLASS_AITER_ASYNC_WITH_ANN, TARGET)
    assert "def __iter__(self) -> synchronicity2.types.SyncOrAsyncIterator[int]:" in code
    assert "def __aiter__(self) -> synchronicity2.types.SyncOrAsyncIterator[int]:" in code

    code = emit_class_from_ir(IR_CLASS_AITER_ASYNC_NO_ANN, TARGET)
    assert "def __iter__(self) -> typing.Any:" in code
    assert "def __aiter__(self) -> typing.Any:" in code

    code = emit_class_from_ir(IR_CLASS_AITER_ASYNC_GEN, TARGET)
    assert "def __iter__(self) -> typing.Generator[float, None, None]:" in code
    assert "def __aiter__(self) -> typing.AsyncGenerator[float, None]:" in code

    code = emit_class_from_ir(IR_CLASS_AITER_ASYNC_ITER_TYPE, TARGET)
    assert "def __iter__(self) -> synchronicity2.types.SyncOrAsyncIterator[bool]:" in code
    assert "def __aiter__(self) -> synchronicity2.types.SyncOrAsyncIterator[bool]:" in code


def test_emit_classproperty_translation():
    ir = ClassWrapperIR(
        impl_ref=ImplQualifiedRef(IMPL, "EmitClassPropertyService"),
        wrapper_ref=WrapperRef(TARGET, "EmitClassPropertyService"),
        wrapped_bases=(),
        generic_type_parameters=None,
        attributes=(),
        properties=(),
        methods=(),
        class_properties=(
            ClassPropertyWrapperIR(
                name="manager",
                return_transformer_ir=WrappedClassTypeIR(
                    impl=ImplQualifiedRef(IMPL, "EmitClassPropertyManager"),
                    wrapper=WrapperRef(TARGET, "EmitClassPropertyManager"),
                ),
            ),
        ),
    )

    code = emit_class_from_ir(ir, TARGET)

    assert '    @classproperty\n    def manager(cls) -> "EmitClassPropertyManager":' in code
    assert "_impl_val = test.unit.compile.test_emit_classes.EmitClassPropertyService.manager" in code
    assert "return EmitClassPropertyManager._from_impl(_impl_val)" in code


def test_emit_classmethod_and_staticmethod_async_context_manager_helper_binding():
    ir = ClassWrapperIR(
        impl_ref=ImplQualifiedRef(IMPL, "EmitContextFactories"),
        wrapper_ref=WrapperRef(TARGET, "EmitContextFactories"),
        wrapped_bases=(),
        generic_type_parameters=None,
        attributes=(),
        properties=(),
        methods=(
            MethodWrapperIR(
                method_name="connect_class",
                method_type=MethodBindingKind.CLASSMETHOD,
                parameters=(),
                is_async_gen=False,
                is_async=False,
                return_transformer_ir=AsyncContextManagerTypeIR(
                    value=WrappedClassTypeIR(
                        impl=ImplQualifiedRef(IMPL, "EmitConnection"),
                        wrapper=WrapperRef(TARGET, "EmitConnection"),
                    )
                ),
            ),
            MethodWrapperIR(
                method_name="connect_static",
                method_type=MethodBindingKind.STATICMETHOD,
                parameters=(),
                is_async_gen=False,
                is_async=False,
                return_transformer_ir=AsyncContextManagerTypeIR(
                    value=WrappedClassTypeIR(
                        impl=ImplQualifiedRef(IMPL, "EmitConnection"),
                        wrapper=WrapperRef(TARGET, "EmitConnection"),
                    )
                ),
            ),
        ),
    )

    code = emit_class_from_ir(ir, TARGET)

    assert "value_wrapper=cls._wrap_async_cm_EmitConnection" in code
    assert "value_wrapper=EmitContextFactories._wrap_async_cm_EmitConnection" in code


def test_emit_sequence_and_callable_ellipsis_annotations():
    ir = ClassWrapperIR(
        impl_ref=ImplQualifiedRef(IMPL, "EmitSequenceCallableService"),
        wrapper_ref=WrapperRef(TARGET, "EmitSequenceCallableService"),
        wrapped_bases=(),
        generic_type_parameters=None,
        attributes=(
            (
                "deps",
                CallableTypeIR(
                    params=None,
                    return_type=SequenceTypeIR(
                        item=WrappedClassTypeIR(
                            impl=ImplQualifiedRef(IMPL, "Node"),
                            wrapper=WrapperRef(TARGET, "Node"),
                        )
                    ),
                ),
            ),
        ),
        properties=(),
        methods=(
            MethodWrapperIR(
                method_name="clone_all",
                method_type=MethodBindingKind.INSTANCE,
                parameters=(
                    ParameterIR(
                        name="nodes",
                        kind=1,
                        annotation_ir=SequenceTypeIR(
                            item=WrappedClassTypeIR(
                                impl=ImplQualifiedRef(IMPL, "Node"),
                                wrapper=WrapperRef(TARGET, "Node"),
                            )
                        ),
                        default_expr=None,
                    ),
                ),
                is_async_gen=False,
                is_async=True,
                return_transformer_ir=AwaitableTypeIR(
                    inner=SequenceTypeIR(
                        item=WrappedClassTypeIR(
                            impl=ImplQualifiedRef(IMPL, "Node"),
                            wrapper=WrapperRef(TARGET, "Node"),
                        )
                    )
                ),
            ),
            MethodWrapperIR(
                method_name="clone_collection",
                method_type=MethodBindingKind.INSTANCE,
                parameters=(
                    ParameterIR(
                        name="nodes",
                        kind=1,
                        annotation_ir=CollectionTypeIR(
                            item=WrappedClassTypeIR(
                                impl=ImplQualifiedRef(IMPL, "Node"),
                                wrapper=WrapperRef(TARGET, "Node"),
                            )
                        ),
                        default_expr=None,
                    ),
                ),
                is_async_gen=False,
                is_async=True,
                return_transformer_ir=AwaitableTypeIR(
                    inner=CollectionTypeIR(
                        item=WrappedClassTypeIR(
                            impl=ImplQualifiedRef(IMPL, "Node"),
                            wrapper=WrapperRef(TARGET, "Node"),
                        )
                    )
                ),
            ),
        ),
    )

    code = emit_class_from_ir(ir, TARGET)

    assert 'def deps(self) -> "typing.Callable[..., ' 'typing.Sequence[Node]]":' in code
    assert 'def clone_all(self, nodes: "typing.Sequence[Node]") -> "typing.Sequence[Node]":' in code
    assert 'def clone_collection(self, nodes: "typing.Collection[Node]") -> "typing.Collection[Node]":' in code
    assert "nodes_impl = [x._impl_instance for x in nodes]" in code


def test_emit_class_without_explicit_init():
    ir = IR_CLASS_NO_INIT
    code = emit_class_from_ir(ir, TARGET)
    assert "def __init__(self):" in code
    assert "def __init__(self, *args, **kwargs):" not in code
    assert f"{IMPL}.{_impl_short(ir)}()" in code


def test_emit_getattr_without_union_fallback_uses_plain_return():
    ir = ClassWrapperIR(
        impl_ref=ImplQualifiedRef(IMPL, "EmitDynamicOwner"),
        wrapper_ref=WrapperRef(TARGET, "EmitDynamicOwner"),
        wrapped_bases=(),
        generic_type_parameters=None,
        attributes=(),
        properties=(),
        methods=(
            MethodWrapperIR(
                method_name="__getattr__",
                method_type=MethodBindingKind.INSTANCE,
                parameters=(
                    ParameterIR(
                        name="name",
                        kind=1,
                        annotation_ir=IdentityTypeIR(signature_text="str"),
                        default_expr=None,
                    ),
                ),
                is_async_gen=False,
                is_async=False,
                return_transformer_ir=IdentityTypeIR(signature_text="typing.Any"),
            ),
        ),
    )

    code = emit_class_from_ir(ir, TARGET)

    assert "return result" in code
    assert "return _wrap_maybe_from_impl(result, _synchronizer)" not in code


def test_emit_getattr_with_union_any_fallback_uses_runtime_fallback_wrap():
    ir = ClassWrapperIR(
        impl_ref=ImplQualifiedRef(IMPL, "EmitExplicitDynamicOwner"),
        wrapper_ref=WrapperRef(TARGET, "EmitExplicitDynamicOwner"),
        wrapped_bases=(),
        generic_type_parameters=None,
        attributes=(),
        properties=(),
        methods=(
            MethodWrapperIR(
                method_name="__getattr__",
                method_type=MethodBindingKind.INSTANCE,
                parameters=(
                    ParameterIR(
                        name="name",
                        kind=1,
                        annotation_ir=IdentityTypeIR(signature_text="str"),
                        default_expr=None,
                    ),
                ),
                is_async_gen=False,
                is_async=False,
                return_transformer_ir=UnionTypeIR(
                    items=(
                        WrappedClassTypeIR(
                            impl=ImplQualifiedRef(IMPL, "EmitPayload"),
                            wrapper=WrapperRef(TARGET, "EmitPayload"),
                        ),
                        IdentityTypeIR(signature_text="typing.Any"),
                    )
                ),
            ),
        ),
    )

    code = emit_class_from_ir(ir, TARGET)

    expected_branch = (
        "EmitPayload._from_impl(_v) if isinstance(_v, test.unit.compile.test_emit_classes.EmitPayload) else _v"
    )
    assert expected_branch in code
