"""Module class for build-time registration of async code.

The Module class provides a lightweight way to mark async functions and classes
for wrapper code generation. It has zero runtime overhead - it simply tracks
what should be wrapped during the build step.
"""

import dataclasses
import typing
from typing import Callable, Optional

F = typing.TypeVar("F")
C = typing.TypeVar("C", bound=type)
D = typing.TypeVar("D")

DEFAULT_SYNCHRONIZER_NAME = "default_synchronizer"
_IMPL_WRAPPER_LOCATION_ATTR = "__synchronicity_wrapper_location__"


@dataclasses.dataclass(frozen=True)
class RegistrationInfo:
    target_module: str
    name: str


@dataclasses.dataclass(frozen=True)
class ManualWrapperRef:
    module: str
    qualname: str


def _default_export_name(source_name: str, *, decorator_name: str) -> str:
    export_name = source_name.lstrip("_")
    if export_name:
        return export_name
    raise ValueError(
        f"{decorator_name}() could not derive a valid export name from source name {source_name!r}; "
        "pass name= explicitly"
    )


def _validate_registration_name(name: str | None, *, decorator_name: str, fallback: str) -> str:
    if name is None:
        return _default_export_name(fallback, decorator_name=decorator_name)
    if not isinstance(name, str):
        raise TypeError(f"{decorator_name}() name must be a string")
    if not name:
        raise ValueError(f"{decorator_name}() name must be a non-empty string")
    if not name.isidentifier():
        raise ValueError(f"{decorator_name}() name must be a valid Python identifier")
    return name


def _impl_ref_from_object(obj: object | None) -> ManualWrapperRef | None:
    if obj is None:
        return None
    module = getattr(obj, "__module__", None)
    qualname = getattr(obj, "__qualname__", None)
    if isinstance(module, str) and isinstance(qualname, str):
        return ManualWrapperRef(module=module, qualname=qualname)
    return None


def _resolve_manual_wrapper_ref(obj: object) -> ManualWrapperRef | None:
    for target in (
        getattr(obj, "sync_wrapper", None),
        getattr(obj, "_sync_impl", None),
        obj.__func__ if isinstance(obj, (classmethod, staticmethod)) else None,
        obj,
    ):
        ref = _impl_ref_from_object(target)
        if ref is not None:
            return ref
    return None


class Module:
    """Lightweight build-time registration for async code wrapper generation.

    The Module class is used to mark async functions and classes that should have
    synchronous wrappers generated. It only exists at build time and has no runtime
    dependencies on the Synchronizer class.

    Example:
        ```python
        from synchronicity2 import Module

        wrapper_module = Module("my_lib")

        @wrapper_module.wrap_function()
        async def my_function():
            return "hello"

        @wrapper_module.wrap_class()
        class MyClass:
            async def my_method(self):
                return "world"
        ```

    Attributes:
        _target_module: The module name where wrapper code will be generated
        _synchronizer_name: Registered name passed to ``get_synchronizer`` for the module-level
            ``_synchronizer`` binding in generated wrapper modules
    """

    def __init__(
        self,
        target_module: Optional[str],
        synchronizer_name: str = DEFAULT_SYNCHRONIZER_NAME,
    ):
        """Initialize a Module for wrapper registration.

        Args:
            target_module: The module name where wrapper code will be generated.
                          Must be provided (auto-detection not yet implemented).
            synchronizer_name: Name passed to ``get_synchronizer(...)`` when generating
                ``_synchronizer = get_synchronizer(...)`` at module scope.
                Defaults to :data:`DEFAULT_SYNCHRONIZER_NAME` (``"default_synchronizer"``).

        Raises:
            NotImplementedError: If target_module is None (auto-detection not supported).
            ValueError: If synchronizer_name is empty.
        """
        if not target_module:
            # TODO: Use call stack to infer calling module, if it's underscored
            # or suffixed with "_impl" -> default to output in same dir
            raise NotImplementedError("Auto module not implemented")
        if not synchronizer_name:
            raise ValueError("synchronizer_name must be a non-empty string")

        self._target_module: str = target_module
        self._synchronizer_name: str = synchronizer_name
        # Instance-level registries - each Module tracks its own wrapped items
        self._wrapped_classes: dict[type, RegistrationInfo] = {}
        self._wrapped_functions: dict[object, RegistrationInfo] = {}
        self._manual_wrappers: dict[int, ManualWrapperRef | None] = {}

    @property
    def target_module(self) -> str:
        """Get the target module name for code generation."""
        return self._target_module

    @property
    def synchronizer_name(self) -> str:
        """Registry name used for the module-level ``_synchronizer`` in generated wrappers."""
        return self._synchronizer_name

    @property
    def _registered_classes(self) -> dict[type, RegistrationInfo]:
        """Get registered classes for this module."""
        return self._wrapped_classes

    @property
    def _registered_functions(self) -> dict[object, RegistrationInfo]:
        """Get registered functions for this module."""
        return self._wrapped_functions

    @property
    def _manual_wrapper_ids(self) -> frozenset[int]:
        """Get object identities registered for manual forwarding in this module."""
        return frozenset(self._manual_wrappers)

    def _is_manual_wrapper(self, obj: object) -> bool:
        """Return whether ``obj`` is registered for manual forwarding in this module."""
        return id(obj) in self._manual_wrappers

    def _manual_wrapper_ref(self, obj: object) -> ManualWrapperRef | None:
        """Get the implementation reference for a manually forwarded object, if any."""
        return self._manual_wrappers.get(id(obj))

    def _module_items(self) -> dict[object, RegistrationInfo]:
        """Get all registered classes and functions with their target module and name.

        Returns:
            Dict mapping registered items (classes or functions) to registration
            metadata for code generation.
        """
        result = {}
        result.update(self._registered_classes)
        result.update(self._registered_functions)
        return result

    def manual_wrapper(self) -> Callable[[D], D]:
        """Decorator to mark an entity for direct forwarding instead of wrapper generation."""

        def decorator(obj: D) -> D:
            self._manual_wrappers[id(obj)] = _resolve_manual_wrapper_ref(obj)
            return obj

        return decorator

    def wrap_function(self, *, name: str | None = None) -> Callable[[F], F]:
        """Decorator to mark a function for wrapper generation."""

        def decorator(fn: F) -> F:
            function_name = getattr(fn, "__name__", None)
            if not isinstance(function_name, str):
                ref = self._manual_wrapper_ref(fn)
                if ref is None:
                    raise TypeError(
                        "wrap_function() expects a function or a @module.manual_wrapper()-registered "
                        "with-aio helper with an underlying implementation reference"
                    )
                function_name = ref.qualname.rpartition(".")[2]
            export_name = _validate_registration_name(
                name,
                decorator_name="wrap_function",
                fallback=function_name,
            )
            self._wrapped_functions[fn] = RegistrationInfo(
                target_module=self._target_module,
                name=export_name,
            )
            return fn

        return decorator

    def wrap_class(self, *, name: str | None = None) -> Callable[[C], C]:
        """Decorator to mark a class for wrapper generation."""

        def decorator(impl_cls: C) -> C:
            export_name = _validate_registration_name(
                name,
                decorator_name="wrap_class",
                fallback=impl_cls.__name__,
            )
            registration = RegistrationInfo(
                target_module=self._target_module,
                name=export_name,
            )
            self._wrapped_classes[impl_cls] = registration

            if self._is_manual_wrapper(impl_cls):
                return impl_cls

            wrapper_location = (self._target_module, export_name)
            existing_location = impl_cls.__dict__.get(_IMPL_WRAPPER_LOCATION_ATTR)
            if existing_location is not None and existing_location != wrapper_location:
                raise RuntimeError(
                    f"Implementation class {impl_cls!r} already has wrapper location {existing_location!r}, "
                    f"cannot replace it with {wrapper_location!r}"
                )

            setattr(impl_cls, _IMPL_WRAPPER_LOCATION_ATTR, wrapper_location)
            return impl_cls

        return decorator
