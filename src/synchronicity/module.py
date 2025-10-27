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

    Note:
        Registration dicts are class-level to persist across module reloads, allowing
        both old and new class objects to be registered (important for TYPE_CHECKING reloads).
    """

    # Class-level registries that persist across module reloads
    _global_registered_classes: dict[type, tuple[str, str]] = {}
    _global_registered_functions: dict[types.FunctionType, tuple[str, str]] = {}

    _target_module: str

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

    @property
    def target_module(self) -> str:
        """Get the target module name for code generation."""
        return self._target_module

    @property
    def _registered_classes(self) -> dict[type, tuple[str, str]]:
        """Get registered classes for this module's target.

        Filters the global registry to return only classes for this target module.
        """
        return {cls: info for cls, info in self._global_registered_classes.items() if info[0] == self._target_module}

    @property
    def _registered_functions(self) -> dict[types.FunctionType, tuple[str, str]]:
        """Get registered functions for this module's target.

        Filters the global registry to return only functions for this target module.
        """
        return {
            func: info for func, info in self._global_registered_functions.items() if info[0] == self._target_module
        }

    def module_items(self) -> dict[typing.Union[type, types.FunctionType], tuple[str, str]]:
        """Get all registered classes and functions with their target module and name.

        Returns:
            Dict mapping registered items (classes or functions) to tuples of
            (target_module, name) for code generation.

        Note:
            If multiple objects (from different reload cycles) map to the same name,
            only the most recent one is returned (deterministic via dict ordering).
        """
        result = {}
        result.update(self._registered_classes)
        result.update(self._registered_functions)

        # Deduplicate by target name (keep most recent registration for each name)
        # Build reverse mapping: (target_module, name) -> object
        by_name: dict[tuple[str, str], typing.Union[type, types.FunctionType]] = {}
        for obj, (target_mod, name) in result.items():
            # Later registrations overwrite earlier ones (desired for reloads)
            by_name[(target_mod, name)] = obj

        # Rebuild result dict with only one object per name
        deduped_result = {}
        for (target_mod, name), obj in by_name.items():
            deduped_result[obj] = (target_mod, name)

        return deduped_result

    def wrap_function(self, f: F) -> F:
        """Decorator to mark a function for wrapper generation.

        This decorator registers the function for wrapper code generation but
        returns it unchanged. It has zero runtime overhead.

        Args:
            f: The function to register for wrapper generation.

        Returns:
            The original function, unchanged.

        Note:
            If a function is registered multiple times (e.g., during module reloads),
            all registrations map to the same target, so this is safe.
        """
        self._global_registered_functions[f] = (self._target_module, f.__name__)
        return f

    def wrap_class(self, cls: C) -> C:
        """Decorator to mark a class for wrapper generation.

        This decorator registers the class for wrapper code generation but
        returns it unchanged. It has zero runtime overhead.

        Args:
            cls: The class to register for wrapper generation.

        Returns:
            The original class, unchanged.

        Note:
            If a class is registered multiple times (e.g., during module reloads),
            all registrations map to the same target, so this is safe.
        """
        self._global_registered_classes[cls] = (self._target_module, cls.__name__)
        return cls
