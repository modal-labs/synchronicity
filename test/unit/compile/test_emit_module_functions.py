"""Unit tests for IR → emitted source (module-level functions).

IR literals below are explicit dataclasses (same shapes as the parse layer). ``IMPL`` is this
module so emitted ``impl_function = ...`` references match assertions.
"""

from __future__ import annotations

from synchronicity.codegen.emitters.sync_async_wrappers import emit_module_level_function
from synchronicity.codegen.ir import ModuleLevelFunctionIR, ParameterIR
from synchronicity.codegen.transformer_ir import (
    AsyncGeneratorTypeIR,
    AwaitableTypeIR,
    CoroutineTypeIR,
    DictTypeIR,
    IdentityTypeIR,
    ImplQualifiedRef,
    ListTypeIR,
    OptionalTypeIR,
    WrappedClassTypeIR,
    WrapperRef,
)

IMPL = __name__
TARGET = "test_module"

# --- Module-level function IR (qualnames are synthetic; shapes match parse output.) ---

IR_FN_ASYNC_GEN = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_async_gen"),
    needs_async_wrapper=True,
    is_async_gen=True,
    parameters=(
        ParameterIR(
            name="items", kind=1, annotation_ir=ListTypeIR(item=IdentityTypeIR(signature_text="str")), default_repr=None
        ),
    ),
    return_transformer_ir=AsyncGeneratorTypeIR(yield_item=IdentityTypeIR(signature_text="str"), send_type_str="None"),
)
IR_FN_BARE_ITERATOR = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_declared_bare_iterator"),
    needs_async_wrapper=True,
    is_async_gen=True,
    parameters=(),
    return_transformer_ir=AsyncGeneratorTypeIR(
        yield_item=IdentityTypeIR(signature_text="typing.Any"), send_type_str="None"
    ),
)
IR_FN_COMPLEX_TYPES = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_complex_types"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(
        ParameterIR(
            name="items", kind=1, annotation_ir=ListTypeIR(item=IdentityTypeIR(signature_text="str")), default_repr=None
        ),
        ParameterIR(
            name="config",
            kind=1,
            annotation_ir=DictTypeIR(
                key=IdentityTypeIR(signature_text="str"), value=IdentityTypeIR(signature_text="int")
            ),
            default_repr=None,
        ),
        ParameterIR(
            name="optional_param",
            kind=1,
            annotation_ir=OptionalTypeIR(inner=IdentityTypeIR(signature_text="str")),
            default_repr="None",
        ),
    ),
    return_transformer_ir=AwaitableTypeIR(
        inner=DictTypeIR(
            key=IdentityTypeIR(signature_text="str"), value=ListTypeIR(item=IdentityTypeIR(signature_text="int"))
        )
    ),
)
IR_FN_CREATE_AWAITABLE = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_create_awaitable"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(ParameterIR(name="x", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),),
    return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="str")),
)
IR_FN_CREATE_AWAITABLE_BARE = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_create_awaitable_bare"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(ParameterIR(name="x", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),),
    return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="typing.Any")),
)
IR_FN_CREATE_COROUTINE = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_create_coroutine"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(ParameterIR(name="x", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),),
    return_transformer_ir=CoroutineTypeIR(return_type=IdentityTypeIR(signature_text="str")),
)
IR_FN_CREATE_PEOPLE = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_create_people"),
    needs_async_wrapper=False,
    is_async_gen=False,
    parameters=(
        ParameterIR(
            name="names", kind=1, annotation_ir=ListTypeIR(item=IdentityTypeIR(signature_text="str")), default_repr=None
        ),
    ),
    return_transformer_ir=ListTypeIR(
        item=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "Person"), wrapper=WrapperRef(TARGET, "Person"))
    ),
)
IR_FN_CREATE_PERSON = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_create_person"),
    needs_async_wrapper=False,
    is_async_gen=False,
    parameters=(
        ParameterIR(name="name", kind=1, annotation_ir=IdentityTypeIR(signature_text="str"), default_repr=None),
    ),
    return_transformer_ir=WrappedClassTypeIR(
        impl=ImplQualifiedRef(IMPL, "Person"), wrapper=WrapperRef(TARGET, "Person")
    ),
)
IR_FN_GENERIC_TYPES = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_generic_types"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(
        ParameterIR(
            name="items", kind=1, annotation_ir=ListTypeIR(item=IdentityTypeIR(signature_text="str")), default_repr=None
        ),
        ParameterIR(
            name="mapping",
            kind=1,
            annotation_ir=DictTypeIR(
                key=IdentityTypeIR(signature_text="str"), value=IdentityTypeIR(signature_text="int")
            ),
            default_repr=None,
        ),
        ParameterIR(
            name="optional_set",
            kind=1,
            annotation_ir=IdentityTypeIR(signature_text="typing.UnionType[set[int], None]"),
            default_repr="None",
        ),
    ),
    return_transformer_ir=AwaitableTypeIR(
        inner=ListTypeIR(
            item=DictTypeIR(key=IdentityTypeIR(signature_text="str"), value=IdentityTypeIR(signature_text="int"))
        )
    ),
)
IR_FN_GREET = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_greet"),
    needs_async_wrapper=False,
    is_async_gen=False,
    parameters=(
        ParameterIR(
            name="person",
            kind=1,
            annotation_ir=WrappedClassTypeIR(
                impl=ImplQualifiedRef(IMPL, "Person"), wrapper=WrapperRef(TARGET, "Person")
            ),
            default_repr=None,
        ),
    ),
    return_transformer_ir=IdentityTypeIR(signature_text="str"),
)
IR_FN_NO_ANNOTATION = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_no_annotation"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(
        ParameterIR(name="x", kind=1, annotation_ir=None, default_repr=None),
        ParameterIR(name="y", kind=1, annotation_ir=None, default_repr="42"),
    ),
    return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="typing.Any")),
)
IR_FN_NO_TYPES = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_no_types"),
    needs_async_wrapper=False,
    is_async_gen=False,
    parameters=(
        ParameterIR(name="x", kind=1, annotation_ir=None, default_repr=None),
        ParameterIR(name="y", kind=1, annotation_ir=None, default_repr=None),
    ),
    return_transformer_ir=IdentityTypeIR(signature_text=""),
)
IR_FN_POSONLY = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_with_posonly"),
    needs_async_wrapper=False,
    is_async_gen=False,
    parameters=(
        ParameterIR(name="a", kind=0, annotation_ir=None, default_repr=None),
        ParameterIR(name="b", kind=0, annotation_ir=None, default_repr=None),
        ParameterIR(name="c", kind=1, annotation_ir=None, default_repr=None),
        ParameterIR(name="d", kind=1, annotation_ir=None, default_repr="10"),
    ),
    return_transformer_ir=IdentityTypeIR(signature_text="int"),
)
IR_FN_SIMPLE_TYPES = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_simple_types"),
    needs_async_wrapper=True,
    is_async_gen=False,
    parameters=(ParameterIR(name="x", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),),
    return_transformer_ir=AwaitableTypeIR(inner=IdentityTypeIR(signature_text="str")),
)
IR_FN_STREAM_BATCHES = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_stream_person_batches"),
    needs_async_wrapper=True,
    is_async_gen=True,
    parameters=(
        ParameterIR(name="batch_size", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),
    ),
    return_transformer_ir=AsyncGeneratorTypeIR(
        yield_item=ListTypeIR(
            item=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "Person"), wrapper=WrapperRef(TARGET, "Person"))
        ),
        send_type_str=None,
    ),
)
IR_FN_STREAM_PEOPLE = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_stream_people"),
    needs_async_wrapper=True,
    is_async_gen=True,
    parameters=(
        ParameterIR(name="count", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),
    ),
    return_transformer_ir=AsyncGeneratorTypeIR(
        yield_item=WrappedClassTypeIR(impl=ImplQualifiedRef(IMPL, "Person"), wrapper=WrapperRef(TARGET, "Person")),
        send_type_str=None,
    ),
)
IR_FN_SYNC_ADD = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_sync_add"),
    needs_async_wrapper=False,
    is_async_gen=False,
    parameters=(
        ParameterIR(name="a", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),
        ParameterIR(name="b", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),
    ),
    return_transformer_ir=IdentityTypeIR(signature_text="int"),
)
IR_FN_VARARGS = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_with_varargs"),
    needs_async_wrapper=False,
    is_async_gen=False,
    parameters=(
        ParameterIR(name="posonly", kind=1, annotation_ir=None, default_repr=None),
        ParameterIR(name="a", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),
        ParameterIR(name="b", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr="10"),
        ParameterIR(name="extra", kind=2, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),
        ParameterIR(name="c", kind=3, annotation_ir=None, default_repr=None),
        ParameterIR(name="extrakwargs", kind=4, annotation_ir=None, default_repr=None),
    ),
    return_transformer_ir=IdentityTypeIR(signature_text="str"),
)
IR_FN_WITH_DEFAULTS = ModuleLevelFunctionIR(
    impl_ref=ImplQualifiedRef(IMPL, "fn_with_defaults"),
    needs_async_wrapper=False,
    is_async_gen=False,
    parameters=(
        ParameterIR(name="a", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr=None),
        ParameterIR(name="b", kind=1, annotation_ir=IdentityTypeIR(signature_text="int"), default_repr="10"),
        ParameterIR(name="c", kind=1, annotation_ir=IdentityTypeIR(signature_text="str"), default_repr="'hello'"),
    ),
    return_transformer_ir=IdentityTypeIR(signature_text="str"),
)


def _fn_short(ir: ModuleLevelFunctionIR) -> str:
    return ir.impl_ref.qualname.rpartition(".")[2]


def test_emit_async_function_basic_template():
    ir = IR_FN_SIMPLE_TYPES
    code = emit_module_level_function(ir, TARGET)
    compile(code, "<string>", "exec")
    name = _fn_short(ir)
    assert f"impl_function = {IMPL}." in code
    assert f"async def __{name}_aio" in code
    assert f"@wrapped_function(__{name}_aio)" in code
    assert f"def {name}" in code
    assert "_run_function_sync" in code
    assert "_run_function_async" in code
    assert "x: int" in code
    assert "-> str" in code


def test_emit_async_function_complex_types():
    code = emit_module_level_function(IR_FN_COMPLEX_TYPES, TARGET)
    compile(code, "<string>", "exec")
    assert "items: list" in code
    assert "config: dict" in code
    assert (
        "optional_param: typing.Union[str, None]" in code
        or "optional_param: str | None" in code
        or "optional_param: typing.Optional" in code
    )
    assert "-> dict" in code
    assert "= None" in code


def test_emit_async_function_no_annotations():
    ir = IR_FN_NO_ANNOTATION
    code = emit_module_level_function(ir, TARGET)
    compile(code, "<string>", "exec")
    n = _fn_short(ir)
    assert f"async def __{n}_aio" in code
    assert f"def {n}" in code


def test_emit_async_function_template_line_order():
    ir = IR_FN_SIMPLE_TYPES
    code = emit_module_level_function(ir, TARGET)
    lines = code.split("\n")
    async_line = next(i for i, line in enumerate(lines) if f"async def __{_fn_short(ir)}_aio" in line)
    assert async_line is not None


def test_emit_async_function_generic_types():
    code = emit_module_level_function(IR_FN_GENERIC_TYPES, TARGET)
    compile(code, "<string>", "exec")
    assert "items: list[str]" in code
    assert "mapping: dict[str, int]" in code
    assert "optional_set:" in code and "set[int]" in code
    assert "-> list[dict[str, int]]" in code
    assert "= None" in code
    assert "async def __" in code
    assert "@wrapped_function" in code
    assert f"impl_function = {IMPL}." in code


def test_emit_async_generator_function():
    """When yield type needs no translation, helpers are skipped and we delegate directly."""
    code = emit_module_level_function(IR_FN_ASYNC_GEN, TARGET)
    compile(code, "<string>", "exec")
    assert "_run_generator_sync" in code
    assert "_run_generator_async" in code
    assert "_run_function_sync" not in code
    # No helper functions needed when yield type doesn't need translation
    assert "_wrap_async_gen" not in code
    # Direct delegation to synchronizer
    assert "_run_generator_async(gen)" in code
    assert "yield from _synchronizer._run_generator_sync(gen)" in code
    assert "_sent = yield _item" in code
    assert "gen = impl_function" in code
    assert "await _wrapped.asend(_sent)" in code
    assert "typing.Generator[str" in code
    assert "typing.AsyncGenerator[str" in code
    assert "items: list" in code


def test_emit_async_generator_template_pattern():
    ir = IR_FN_ASYNC_GEN
    code = emit_module_level_function(ir, TARGET)
    name = _fn_short(ir)
    assert f"async def __{name}_aio" in code
    assert f"@wrapped_function(__{name}_aio)" in code
    assert f"def {name}" in code
    assert "gen = impl_function(" in code
    assert "_sent = yield _item" in code
    assert "await _wrapped.asend(_sent)" in code


def test_emit_async_generator_wrapped_yield_type_quoting():
    code = emit_module_level_function(IR_FN_STREAM_PEOPLE, TARGET)
    compile(code, "<string>", "exec")
    assert ' -> "typing.Generator[Person, None, None]"' in code
    assert ' -> "typing.AsyncGenerator[Person]"' in code
    assert 'Generator["Person"' not in code
    assert 'AsyncGenerator["Person"' not in code


def test_emit_async_generator_nested_wrapped_yield_quoting():
    code = emit_module_level_function(IR_FN_STREAM_BATCHES, TARGET)
    compile(code, "<string>", "exec")
    assert ' -> "typing.Generator[list[Person], None, None]"' in code
    assert ' -> "typing.AsyncGenerator[list[Person]]"' in code


def test_emit_declared_bare_iterator():
    code = emit_module_level_function(IR_FN_BARE_ITERATOR, TARGET)
    assert 'async def __fn_declared_bare_iterator_aio() -> "typing.AsyncGenerator[typing.Any, None]"' in code
    assert "@wrapped_function" in code
    assert 'def fn_declared_bare_iterator() -> "typing.Generator[typing.Any, None, None]"' in code


def test_emit_sync_function_basic():
    code = emit_module_level_function(IR_FN_SYNC_ADD, TARGET)
    compile(code, "<string>", "exec")
    assert "await impl_function" not in code
    assert "_run_function_sync" not in code
    assert "_run_function_async" not in code
    assert "return impl_function(a, b)" in code
    assert "class _simple_add" not in code
    assert "@wrapped_function" not in code
    assert "async def aio" not in code


def test_emit_sync_function_wrapped_arg():
    code = emit_module_level_function(IR_FN_GREET, TARGET)
    compile(code, "<string>", "exec")
    assert "person_impl = person._impl_instance" in code
    assert "return impl_function(person_impl)" in code
    assert "_run_function_sync" not in code
    assert "class _greet" not in code
    assert "@wrapped_function" not in code


def test_emit_sync_function_wrapped_return():
    code = emit_module_level_function(IR_FN_CREATE_PERSON, TARGET)
    compile(code, "<string>", "exec")
    assert "result = impl_function(name)" in code
    assert "return Person._from_impl(result)" in code
    assert "_run_function_sync" not in code
    assert "class _create_person" not in code


def test_emit_sync_function_list_wrapped_return():
    code = emit_module_level_function(IR_FN_CREATE_PEOPLE, TARGET)
    compile(code, "<string>", "exec")
    assert "result = impl_function(names)" in code
    assert "[Person._from_impl(x) for x in result]" in code
    assert "_run_function_sync" not in code
    assert "class _create_people" not in code


def test_emit_sync_function_no_annotations():
    code = emit_module_level_function(IR_FN_NO_TYPES, TARGET)
    compile(code, "<string>", "exec")
    assert "return impl_function(x, y)" in code
    assert "_run_function_sync" not in code


def test_emit_sync_function_default_args():
    code = emit_module_level_function(IR_FN_WITH_DEFAULTS, TARGET)
    compile(code, "<string>", "exec")
    assert "b: int = 10" in code
    assert "c: str = 'hello'" in code
    assert "return impl_function(a, b, c)" in code


def test_emit_function_varargs():
    code = emit_module_level_function(IR_FN_VARARGS, TARGET)
    assert "def fn_with_varargs(posonly, a: int, b: int = 10, *extra: int, c, **extrakwargs)" in code
    assert "return impl_function(posonly, a, b, *extra, c=c, **extrakwargs)" in code
    compile(code, "<string>", "exec")


def test_emit_function_positional_only():
    code = emit_module_level_function(IR_FN_POSONLY, TARGET)
    assert "def fn_with_posonly(a, b, /, c, d = 10)" in code
    assert "return impl_function(a, b, c, d)" in code
    compile(code, "<string>", "exec")


def test_emit_sync_function_returning_coroutine():
    code = emit_module_level_function(IR_FN_CREATE_COROUTINE, TARGET)
    assert "@wrapped_function" in code
    assert "async def __fn_create_coroutine_aio(x: int) -> str" in code
    assert "def fn_create_coroutine(x: int) -> str" in code
    assert "_run_function_sync" in code
    assert "_run_function_async" in code


def test_emit_sync_function_returning_awaitable():
    code = emit_module_level_function(IR_FN_CREATE_AWAITABLE, TARGET)
    assert "@wrapped_function" in code
    assert "async def __fn_create_awaitable_aio(x: int) -> str" in code
    assert "def fn_create_awaitable(x: int) -> str" in code
    assert "_run_function_sync" in code
    assert "_run_function_async" in code


def test_emit_sync_function_returning_bare_awaitable():
    code = emit_module_level_function(IR_FN_CREATE_AWAITABLE_BARE, TARGET)
    assert "@wrapped_function" in code
    assert "async def __fn_create_awaitable_bare_aio(x: int) -> typing.Any" in code
    assert "def fn_create_awaitable_bare(x: int) -> typing.Any" in code
    assert "_run_function_sync" in code
    assert "_run_function_async" in code
