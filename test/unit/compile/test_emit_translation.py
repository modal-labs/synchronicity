"""IR → code tests for unwrap/wrap and translation-shaped emission.

IR literals live in this module. ``IMPL`` is this module name for emitted references.
"""

from __future__ import annotations

from synchronicity2.codegen.emitters.sync_async_wrappers import emit_class_from_ir, emit_module_level_function
from synchronicity2.codegen.ir import (
    ClassWrapperIR,
    MethodBindingKind,
    MethodWrapperIR,
    ModuleLevelFunctionIR,
    ParameterIR,
)
from synchronicity2.codegen.transformer_ir import (
    AsyncGeneratorTypeIR,
    AwaitableTypeIR,
    IdentityTypeIR,
    ImplQualifiedRef,
    ListTypeIR,
    OptionalTypeIR,
    TupleTypeIR,
    WrappedClassTypeIR,
    WrapperRef,
)

IMPL = __name__
TARGET = "test_module"

IR_CLASS_HELPER = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "HelperTestClass"),
    wrapper_ref=WrapperRef(TARGET, "HelperTestClass"),
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
    ),
)
IR_CLASS_HELPER_SUBCLASS = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "HelperTestSubclass"),
    wrapper_ref=WrapperRef(TARGET, "HelperTestSubclass"),
    wrapped_bases=((ImplQualifiedRef(IMPL, "HelperTestClass"), WrapperRef(TARGET, "HelperTestClass")),),
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
    ),
)
IR_FN_NODE_GENERATOR = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_node_generator"),
    needs_async_wrapper=True,
    is_async_gen=True,
    parameters=(),
    return_transformer_ir=AsyncGeneratorTypeIR(
        yield_item=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "GenNode"), wrapper=WrapperRef(TARGET, "GenNode")),
        send_type_str="None",
    ),
)
IR_FN_RETURNS_STRING = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_returns_string"),
    needs_async_wrapper=False,
    is_async_gen=False,
    parameters=(),
    return_transformer_ir=IdentityTypeIR(signature_text="str"),
)
IR_FN_SIMPLE_GEN = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_simple_gen"),
    needs_async_wrapper=True,
    is_async_gen=True,
    parameters=(),
    return_transformer_ir=AsyncGeneratorTypeIR(yield_item=IdentityTypeIR(signature_text="str"), send_type_str="None"),
)
IR_FN_TUPLE_GENERATORS = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_tuple_generators"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(),
    return_transformer_ir=AwaitableTypeIR(
        inner=TupleTypeIR(
            elements=(
                AsyncGeneratorTypeIR(yield_item=IdentityTypeIR(signature_text="str"), send_type_str="None"),
                AsyncGeneratorTypeIR(yield_item=IdentityTypeIR(signature_text="int"), send_type_str="None"),
            ),
            variadic=False,
        )
    ),
)
IR_TR_CONNECT_NODES = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "tr_connect_nodes"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(
        ParameterIR(
            name="parent",
            kind=1,
            annotation_ir=WrappedClassTypeIR(
                impl=ImplQualifiedRef(IMPL, "TestNode"), wrapper=WrapperRef(TARGET, "TestNode")
            ),
            default_expr=None,
        ),
        ParameterIR(
            name="child",
            kind=1,
            annotation_ir=WrappedClassTypeIR(
                impl=ImplQualifiedRef(IMPL, "TestNode"), wrapper=WrapperRef(TARGET, "TestNode")
            ),
            default_expr=None,
        ),
    ),
    return_transformer_ir=AwaitableTypeIR(
        inner=TupleTypeIR(
            elements=(
                WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode"), wrapper=WrapperRef(TARGET, "TestNode")),
                WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode"), wrapper=WrapperRef(TARGET, "TestNode")),
            ),
            variadic=False,
        )
    ),
)
IR_TR_CREATE_NODE = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "tr_create_node"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(
        ParameterIR(name="value", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_expr=None),
    ),
    return_transformer_ir=AwaitableTypeIR(
        inner=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode"), wrapper=WrapperRef(TARGET, "TestNode"))
    ),
)
IR_TR_GET_NODE_LIST = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "tr_get_node_list"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(
        ParameterIR(
            name="nodes",
            kind=1,
            annotation_ir=ListTypeIR(
                item=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode"), wrapper=WrapperRef(TARGET, "TestNode"))
            ),
            default_expr=None,
        ),
    ),
    return_transformer_ir=AwaitableTypeIR(
        inner=ListTypeIR(
            item=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode"), wrapper=WrapperRef(TARGET, "TestNode"))
        )
    ),
)
IR_TR_GET_OPTIONAL_NODE = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "tr_get_optional_node"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(
        ParameterIR(
            name="node",
            kind=1,
            annotation_ir=OptionalTypeIR(
                inner=WrappedClassTypeIR(
                    impl=ImplQualifiedRef(IMPL, "TestNode"), wrapper=WrapperRef(TARGET, "TestNode")
                )
            ),
            default_expr=None,
        ),
    ),
    return_transformer_ir=AwaitableTypeIR(
        inner=OptionalTypeIR(
            inner=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode"), wrapper=WrapperRef(TARGET, "TestNode"))
        )
    ),
)
IR_TR_PROCESS_LIST = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "tr_process_list"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(
        ParameterIR(
            name="nodes",
            kind=1,
            annotation_ir=ListTypeIR(
                item=WrappedClassTypeIR(
                    impl=ImplQualifiedRef(IMPL, "CollectionTestNode"), wrapper=WrapperRef(TARGET, "CollectionTestNode")
                )
            ),
            default_expr=None,
        ),
    ),
    return_transformer_ir=AwaitableTypeIR(
        inner=ListTypeIR(
            item=WrappedClassTypeIR(
                impl=ImplQualifiedRef(IMPL, "CollectionTestNode"), wrapper=WrapperRef(TARGET, "CollectionTestNode")
            )
        )
    ),
)
IR_TR_PROCESS_NODE = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "tr_process_node"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(
        ParameterIR(
            name="node",
            kind=1,
            annotation_ir=WrappedClassTypeIR(
                impl=ImplQualifiedRef(IMPL, "UnwrapTestNode"), wrapper=WrapperRef(TARGET, "UnwrapTestNode")
            ),
            default_expr=None,
        ),
    ),
    return_transformer_ir=AwaitableTypeIR(
        inner=WrappedClassTypeIR(
            impl=ImplQualifiedRef(IMPL, "UnwrapTestNode"), wrapper=WrapperRef(TARGET, "UnwrapTestNode")
        )
    ),
)
IR_TR_TESTNODE_CLASS = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "TestNode"),
    wrapper_ref=WrapperRef(TARGET, "TestNode"),
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
            method_name="create_child",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(
                    name="child_value", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_expr=None
                ),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="'TestNode'")),
        ),
    ),
)


def test_emit_translation_function_and_class_signatures():
    create_node_code = emit_module_level_function(IR_TR_CREATE_NODE, TARGET)
    connect_nodes_code = emit_module_level_function(IR_TR_CONNECT_NODES, TARGET)
    get_node_list_code = emit_module_level_function(IR_TR_GET_NODE_LIST, TARGET)
    get_optional_node_code = emit_module_level_function(IR_TR_GET_OPTIONAL_NODE, TARGET)
    class_code = emit_class_from_ir(IR_TR_TESTNODE_CLASS, TARGET)

    assert "_instance_cache: weakref.WeakValueDictionary" in class_code
    assert "def _from_impl(cls, impl_instance: typing.Any)" in class_code
    assert "_wrapped_from_impl(cls, impl_instance, cls._instance_cache, _synchronizer)" in class_code

    assert (
        'def tr_create_node(value: int) -> "TestNode":' in create_node_code
        or "def tr_create_node(value: int) -> 'TestNode':" in create_node_code
    )
    assert (
        'def tr_get_node_list(nodes: list[TestNode]) -> "list[TestNode]":' in get_node_list_code
        or "def tr_get_node_list(nodes: list[TestNode]) -> 'list[TestNode]':" in get_node_list_code
    )
    assert (
        'def tr_get_optional_node(node: typing.Union[TestNode, None]) -> "typing.Union[TestNode, None]":'
        in get_optional_node_code
        or "def tr_get_optional_node(node: typing.Union[TestNode, None]) -> 'typing.Union[TestNode, None]':"
        in get_optional_node_code
    )
    assert (
        'def tr_connect_nodes(parent: "TestNode", child: "TestNode") -> "tuple[TestNode, TestNode]":'
        in connect_nodes_code
        or "def tr_connect_nodes(parent: 'TestNode', child: 'TestNode') -> 'tuple[TestNode, TestNode]':"
        in connect_nodes_code
    )

    assert "parent_impl = parent._impl_instance" in connect_nodes_code
    assert "child_impl = child._impl_instance" in connect_nodes_code
    assert "TestNode._from_impl(" in connect_nodes_code


def test_emit_wrapper_helpers():
    compiled_code = emit_class_from_ir(IR_CLASS_HELPER, TARGET)
    assert "_instance_cache: weakref.WeakValueDictionary = weakref.WeakValueDictionary()" in compiled_code
    assert "def _from_impl(cls, impl_instance: typing.Any)" in compiled_code
    assert "_wrapped_from_impl(cls, impl_instance, cls._instance_cache, _synchronizer)" in compiled_code


def test_emit_subclass_wrapper_helpers_reuse_root_cache():
    compiled_code = emit_class_from_ir(IR_CLASS_HELPER_SUBCLASS, TARGET)
    assert "class HelperTestSubclass(HelperTestClass):" in compiled_code
    assert "def _from_impl(cls, impl_instance: typing.Any)" in compiled_code
    assert '-> "HelperTestSubclass":' in compiled_code or "-> 'HelperTestSubclass':" in compiled_code
    assert "_wrapped_from_impl(cls, impl_instance, cls._instance_cache, _synchronizer)" in compiled_code
    assert "WeakValueDictionary = weakref.WeakValueDictionary()" not in compiled_code


def test_emit_unwrap_in_function_bodies():
    compiled_code = emit_module_level_function(IR_TR_PROCESS_NODE, TARGET)
    assert "node_impl = node._impl_instance" in compiled_code
    assert "return UnwrapTestNode._from_impl(result)" in compiled_code


def test_emit_collection_translation():
    compiled_code = emit_module_level_function(IR_TR_PROCESS_LIST, TARGET)
    assert "[x._impl_instance for x in nodes]" in compiled_code
    assert "[CollectionTestNode._from_impl(x) for x in " in compiled_code


def test_emit_primitives_no_impl_suffix():
    compiled_code = emit_module_level_function(IR_FN_RETURNS_STRING, TARGET)
    assert "str._from_impl" not in compiled_code


def test_emit_async_generator_wrapping_helpers():
    """When yield type needs no translation, helpers are skipped; direct synchronizer delegation."""
    compiled_code = emit_module_level_function(IR_FN_SIMPLE_GEN, TARGET)
    # No helper functions needed for identity yield types
    assert "_wrap_async_gen" not in compiled_code
    # Direct delegation to synchronizer
    assert "_synchronizer._run_generator_async(gen)" in compiled_code
    assert "yield from _synchronizer._run_generator_sync(gen)" in compiled_code
    assert "await _wrapped.asend(_sent)" in compiled_code
    assert "await _wrapped.aclose()" in compiled_code
    assert "async def aio(self)" in compiled_code
    assert '-> "typing.Generator[str, None, None]":' in compiled_code
    assert '-> "typing.AsyncGenerator[str, None]":' in compiled_code


def test_emit_tuple_of_generators():
    """Tuple of generators with identity yield types uses direct synchronizer delegation."""
    compiled_code = emit_module_level_function(IR_FN_TUPLE_GENERATORS, TARGET)
    # No helper functions needed for identity yield types
    assert "_wrap_async_gen" not in compiled_code
    # Direct delegation in tuple construction
    assert "_synchronizer._run_generator_async(result[0])" in compiled_code
    assert "_synchronizer._run_generator_async(result[1])" in compiled_code
    assert "_synchronizer._run_generator_sync(result[0])" in compiled_code
    assert "_synchronizer._run_generator_sync(result[1])" in compiled_code
    assert (
        'def fn_tuple_generators() -> "tuple[typing.Generator[str, None, None], typing.Generator[int, None, None]]":'
        in compiled_code
    )
    assert (
        "async def aio(self) -> "
        '"tuple[typing.AsyncGenerator[str, None], typing.AsyncGenerator[int, None]]":' in compiled_code
    )


def test_emit_generator_with_wrapped_yield_type():
    compiled_code = emit_module_level_function(IR_FN_NODE_GENERATOR, TARGET)
    assert "_wrap_async_gen" in compiled_code
    assert "GenNode._from_impl(_item)" in compiled_code
    assert "async def _wrap_async_gen" in compiled_code
    assert "def _wrap_async_gen" in compiled_code
