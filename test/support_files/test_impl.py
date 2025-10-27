"""Test implementation module for translation integration tests."""

import typing

from synchronicity import Module

wrapper_module = Module("test_lib")


@wrapper_module.wrap_class
class _ImplPerson:
    """Implementation class for testing."""

    def __init__(self, name: str):
        self.name = name

    async def greet(self, other: "_ImplPerson") -> str:
        return f"{self.name} greets {other.name}"

    async def get_friends(self) -> "typing.List[_ImplPerson]":
        return [_ImplPerson("Alice"), _ImplPerson("Bob")]


@wrapper_module.wrap_function
async def accepts_person(p: _ImplPerson) -> _ImplPerson:
    """Test function that accepts and returns a Person."""
    return p


@wrapper_module.wrap_function
async def accepts_list_of_persons(persons: typing.List[_ImplPerson]) -> typing.List[_ImplPerson]:
    """Test function with list of persons."""
    return persons


@wrapper_module.wrap_function
async def accepts_optional_person(p: typing.Optional[_ImplPerson]) -> typing.Optional[_ImplPerson]:
    """Test function with optional person."""
    return p


@wrapper_module.wrap_function
async def accepts_dict_of_persons(persons: typing.Dict[str, _ImplPerson]) -> typing.Dict[str, _ImplPerson]:
    """Test function with dict of persons."""
    return persons
