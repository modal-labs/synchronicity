"""Module class for build-time registration of async code.

The Module class provides a lightweight way to mark async functions and classes
for wrapper code generation. It has zero runtime overhead - it simply tracks
what should be wrapped during the build step.
"""

import types
import typing
from typing import Callable, Optional

T = typing.TypeVar("T", bound=typing.Union[type, Callable])
F = typing.TypeVar("F", bound=types.FunctionType)
C = typing.TypeVar("C", bound=type)


class Module:
    """Lightweight build-time registration for async code wrapper generation.

    The Module class is used to mark async functions and classes that should have
    synchronous wrappers generated. It only exists at build time and has no runtime
    dependencies on the Synchronizer class.

    Example:
        ```python
        from synchronicity import Module

        wrapper_module = Module("my_lib")

        @wrapper_module.wrap_function
        async def my_function():
            return "hello"

        @wrapper_module.wrap_class
        class MyClass:
            async def my_method(self):
                return "world"
        ```

    Attributes:
        _target_module: The module name where wrapper code will be generated
    """

    def __init__(self, target_module: Optional[str]):
        """Initialize a Module for wrapper registration.

        Args:
            target_module: The module name where wrapper code will be generated.
                          Must be provided (auto-detection not yet implemented).

        Raises:
            NotImplementedError: If target_module is None (auto-detection not supported).
        """
        if not target_module:
            # TODO: Use call stack to infer calling module, if it's underscored
            # or suffixed with "_impl" -> default to output in same dir
            raise NotImplementedError("Auto module not implemented")

        self._target_module: str = target_module
        # Instance-level registries - each Module tracks its own wrapped items
        self._wrapped_classes: dict[type, tuple[str, str]] = {}
        self._wrapped_functions: dict[types.FunctionType, tuple[str, str]] = {}

    @property
    def target_module(self) -> str:
        """Get the target module name for code generation."""
        return self._target_module

    @property
    def _registered_classes(self) -> dict[type, tuple[str, str]]:
        """Get registered classes for this module."""
        return self._wrapped_classes

    @property
    def _registered_functions(self) -> dict[types.FunctionType, tuple[str, str]]:
        """Get registered functions for this module."""
        return self._wrapped_functions

    def module_items(self) -> dict[typing.Union[type, types.FunctionType], tuple[str, str]]:
        """Get all registered classes and functions with their target module and name.

        Returns:
            Dict mapping registered items (classes or functions) to tuples of
            (target_module, name) for code generation.
        """
        result = {}
        result.update(self._registered_classes)
        result.update(self._registered_functions)
        return result

    def wrap_function(self, f: F) -> F:
        """Decorator to mark a function for wrapper generation.

        This decorator registers the function for wrapper code generation but
        returns it unchanged. It has zero runtime overhead.

        Args:
            f: The function to register for wrapper generation.

        Returns:
            The original function, unchanged.
        """
        self._wrapped_functions[f] = (self._target_module, f.__name__)
        return f

    def wrap_class(self, cls: C) -> C:
        """Decorator to mark a class for wrapper generation.

        This decorator registers the class for wrapper code generation but
        returns it unchanged. It has zero runtime overhead.

        Args:
            cls: The class to register for wrapper generation.

        Returns:
            The original class, unchanged.
        """
        self._wrapped_classes[cls] = (self._target_module, cls.__name__)
        return cls
