from typing import List

from synchronicity import Synchronizer
from synchronicity.genstub import StubEmitter


def test_module_assignment():
    s = Synchronizer()
    class Foo:
        pass

    BFoo = s.create_blocking(Foo, "BFoo", "mymod")
    assert s._target_modules == {"mymod": {"BFoo": BFoo}}


def noop():
    pass

def arg_no_anno(arg1):
    pass

def scalar_args(arg1: str, arg2: int) -> float:
    pass

from .genstub_helpers import some_mod
def generic_other_module_arg(arg: List[some_mod.Foo]):
    pass

def test_function_stub():
    stub_emitter = StubEmitter("dummy")
    stub_emitter.add_function(noop)
    assert stub_emitter.get_source() == "def noop():\n    ...\n"

    stub_emitter = StubEmitter("dummy")
    stub_emitter.add_function(arg_no_anno)
    assert stub_emitter.get_source() == "def arg_no_anno(arg1):\n    ...\n"

    stub_emitter = StubEmitter("dummy")
    stub_emitter.add_function(scalar_args)
    assert stub_emitter.get_source() == "def scalar_args(arg1: str, arg2: int) -> float:\n    ...\n"

    stub_emitter = StubEmitter("dummy")
    stub_emitter.add_function(generic_other_module_arg)
    assert stub_emitter.get_source() == """import test.genstub_helpers.some_mod
import typing

def generic_other_module_arg(arg: List[test.genstub_helpers.some_mod.Foo]):
    ...
"""
