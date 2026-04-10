"""IR → code tests for unwrap/wrap and translation-shaped emission.

IR literals live in this module. ``IMPL`` is this module name for emitted references.
"""

from __future__ import annotations

from synchronicity.codegen.emitters.sync_async_wrappers import emit_class_from_ir, emit_module_level_function
from synchronicity.codegen.ir import (
    ClassWrapperIR,
    MethodBindingKind,
    MethodWrapperIR,
    ModuleLevelFunctionIR,
    ParameterIR,
)
from synchronicity.codegen.sync_registry import SyncRegistry
from synchronicity.codegen.transformer_ir import (
    AsyncGeneratorTypeIR,
    AwaitableTypeIR,
    IdentityTypeIR,
    ImplQualifiedRef,
    ListTypeIR,
    OptionalTypeIR,
    TupleTypeIR,
    WrappedClassTypeIR,
)

IMPL = __name__
TARGET = "test_module"

IR_CLASS_HELPER = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "HelperTestClass"),
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
    ),
)
IR_CLASS_HELPER_SUBCLASS = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "HelperTestSubclass"),
    wrapped_base_impl_refs=(ImplQualifiedRef(IMPL, "HelperTestClass"),),
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
    ),
)
IR_FN_NODE_GENERATOR = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_node_generator"),
    needs_async_wrapper=True,
    is_async_gen=True,
    parameters=(),
    return_transformer_ir=AsyncGeneratorTypeIR(
        yield_item=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "GenNode")), send_type_str="None"
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
            annotation_ir=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode")),
            default_repr=None,
        ),
        ParameterIR(
            name="child",
            kind=1,
            annotation_ir=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode")),
            default_repr=None,
        ),
    ),
    return_transformer_ir=AwaitableTypeIR(
        inner=TupleTypeIR(
            elements=(
                WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode")),
                WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode")),
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
        ParameterIR(name="value", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),
    ),
    return_transformer_ir=AwaitableTypeIR(inner=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode"))),
)
IR_TR_GET_NODE_LIST = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "tr_get_node_list"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(
        ParameterIR(
            name="nodes",
            kind=1,
            annotation_ir=ListTypeIR(item=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode"))),
            default_repr=None,
        ),
    ),
    return_transformer_ir=AwaitableTypeIR(
        inner=ListTypeIR(item=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode")))
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
            annotation_ir=OptionalTypeIR(inner=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode"))),
            default_repr=None,
        ),
    ),
    return_transformer_ir=AwaitableTypeIR(
        inner=OptionalTypeIR(inner=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "TestNode")))
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
            annotation_ir=ListTypeIR(item=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "CollectionTestNode"))),
            default_repr=None,
        ),
    ),
    return_transformer_ir=AwaitableTypeIR(
        inner=ListTypeIR(item=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "CollectionTestNode")))
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
            annotation_ir=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "UnwrapTestNode")),
            default_repr=None,
        ),
    ),
    return_transformer_ir=AwaitableTypeIR(inner=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "UnwrapTestNode"))),
)
IR_TR_TESTNODE_CLASS = ClassWrapperIR(
    impl_ref=ImplQualifiedRef(IMPL, "TestNode"),
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
            method_name="create_child",
            method_type=MethodBindingKind.INSTANCE,
            parameters=(
                ParameterIR(
                    name="child_value", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None
                ),
            ),
            is_async_gen=False,
            is_async=True,
            return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="'TestNode'")),
        ),
    ),
)

REG_EMPTY = SyncRegistry({})

REG_PERSON = SyncRegistry(
    {
        ImplQualifiedRef(IMPL, "Person"): (TARGET, "Person"),
    }
)

REG_GENNODE = SyncRegistry(
    {
        ImplQualifiedRef(IMPL, "GenNode"): (TARGET, "GenNode"),
    }
)

REG_TESTNODE = SyncRegistry(
    {
        ImplQualifiedRef(IMPL, "TestNode"): (TARGET, "TestNode"),
    }
)

REG_HELPER = SyncRegistry(
    {
        ImplQualifiedRef(IMPL, "HelperTestClass"): (TARGET, "HelperTestClass"),
        ImplQualifiedRef(IMPL, "HelperTestSubclass"): (TARGET, "HelperTestSubclass"),
    }
)

REG_UNWRAP = SyncRegistry(
    {
        ImplQualifiedRef(IMPL, "UnwrapTestNode"): (TARGET, "UnwrapTestNode"),
    }
)

REG_COLL = SyncRegistry(
    {
        ImplQualifiedRef(IMPL, "CollectionTestNode"): (TARGET, "CollectionTestNode"),
    }
)


def test_emit_translation_function_and_class_signatures():
    sync = REG_TESTNODE
    create_node_code = emit_module_level_function(IR_TR_CREATE_NODE, sync, TARGET)
    connect_nodes_code = emit_module_level_function(IR_TR_CONNECT_NODES, sync, TARGET)
    get_node_list_code = emit_module_level_function(IR_TR_GET_NODE_LIST, sync, TARGET)
    get_optional_node_code = emit_module_level_function(IR_TR_GET_OPTIONAL_NODE, sync, TARGET)
    class_code = emit_class_from_ir(IR_TR_TESTNODE_CLASS, sync, TARGET)

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
    compiled_code = emit_class_from_ir(IR_CLASS_HELPER, REG_HELPER, TARGET)
    assert "_instance_cache: weakref.WeakValueDictionary = weakref.WeakValueDictionary()" in compiled_code
    assert "def _from_impl(cls, impl_instance: typing.Any)" in compiled_code
    assert "_wrapped_from_impl(cls, impl_instance, cls._instance_cache, _synchronizer)" in compiled_code


def test_emit_subclass_wrapper_helpers_reuse_root_cache():
    compiled_code = emit_class_from_ir(IR_CLASS_HELPER_SUBCLASS, REG_HELPER, TARGET)
    assert "class HelperTestSubclass(HelperTestClass):" in compiled_code
    assert "def _from_impl(cls, impl_instance: typing.Any)" in compiled_code
    assert '-> "HelperTestSubclass":' in compiled_code or "-> 'HelperTestSubclass':" in compiled_code
    assert "_wrapped_from_impl(cls, impl_instance, cls._instance_cache, _synchronizer)" in compiled_code
    assert "WeakValueDictionary = weakref.WeakValueDictionary()" not in compiled_code


def test_emit_unwrap_in_function_bodies():
    compiled_code = emit_module_level_function(IR_TR_PROCESS_NODE, REG_UNWRAP, TARGET)
    assert "node_impl = node._impl_instance" in compiled_code
    assert "return UnwrapTestNode._from_impl(result)" in compiled_code


def test_emit_collection_translation():
    compiled_code = emit_module_level_function(IR_TR_PROCESS_LIST, REG_COLL, TARGET)
    assert "[x._impl_instance for x in nodes]" in compiled_code
    assert "[CollectionTestNode._from_impl(x) for x in " in compiled_code


def test_emit_primitives_no_impl_suffix():
    compiled_code = emit_module_level_function(IR_FN_RETURNS_STRING, REG_EMPTY, TARGET)
    assert "str._from_impl" not in compiled_code


def test_emit_async_generator_wrapping_helpers():
    compiled_code = emit_module_level_function(IR_FN_SIMPLE_GEN, REG_EMPTY, TARGET)
    assert "_wrap_async_gen_str" in compiled_code
    assert "_wrap_async_gen_str_sync" in compiled_code
    assert "async def _wrap_async_gen_str(_gen):" in compiled_code
    assert "await _wrapped.asend(_sent)" in compiled_code
    assert "await _wrapped.aclose()" in compiled_code
    assert "def _wrap_async_gen_str_sync(_gen):" in compiled_code
    assert "yield from _synchronizer._run_generator_sync(_gen)" in compiled_code
    assert "async def __fn_simple_gen_aio" in compiled_code or "async def __" in compiled_code
    assert '-> "typing.Generator[str, None, None]":' in compiled_code
    assert '-> "typing.AsyncGenerator[str, None]":' in compiled_code


def test_emit_tuple_of_generators():
    compiled_code = emit_module_level_function(IR_FN_TUPLE_GENERATORS, REG_EMPTY, TARGET)
    assert "_wrap_async_gen_str" in compiled_code
    assert "_wrap_async_gen_int" in compiled_code
    assert "_wrap_async_gen_str_sync" in compiled_code
    assert "_wrap_async_gen_int_sync" in compiled_code
    assert (
        'def fn_tuple_generators() -> "tuple[typing.Generator[str, None, None], typing.Generator[int, None, None]]":'
        in compiled_code
    )
    assert (
        "async def __fn_tuple_generators_aio() -> "
        '"tuple[typing.AsyncGenerator[str, None], typing.AsyncGenerator[int, None]]":' in compiled_code
    )
    assert "self._wrap_async_gen_str_sync" in compiled_code or "_wrap_async_gen_str_sync" in compiled_code
    assert "self._wrap_async_gen_int_sync" in compiled_code or "_wrap_async_gen_int_sync" in compiled_code
    assert "self._wrap_async_gen_str" in compiled_code or "_wrap_async_gen_str(" in compiled_code
    assert "self._wrap_async_gen_int" in compiled_code or "_wrap_async_gen_int(" in compiled_code


def test_emit_generator_with_wrapped_yield_type():
    compiled_code = emit_module_level_function(IR_FN_NODE_GENERATOR, REG_GENNODE, TARGET)
    assert "_wrap_async_gen" in compiled_code
    assert "GenNode._from_impl(_item)" in compiled_code
    assert "async def _wrap_async_gen" in compiled_code
    assert "def _wrap_async_gen" in compiled_code
