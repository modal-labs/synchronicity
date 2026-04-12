"""Serialize typing.TypeVar / ParamSpec into primitive specs and source lines."""

from __future__ import annotations

import typing

from synchronicity.module import _IMPL_WRAPPER_LOCATION_ATTR

from .ir import TypeVarSpecIR
from .transformer_ir import TypeTransformerIR, WrappedClassTypeIR, WrapperRef
from .transformer_materialize import resolve_typevar_bound_to_wrapped_impl


def _get_wrapper_location(t: type) -> tuple[str, str] | None:
    return getattr(t, _IMPL_WRAPPER_LOCATION_ATTR, None)


def translate_typevar_bound(
    bound: type | str,
    known_impl_types: frozenset[type],
    target_module: str,
    *,
    impl_modules: frozenset[str] | None = None,
) -> str:
    def _iter_matching_name(name: str):
        for impl_type in known_impl_types:
            if impl_type.__name__ != name:
                continue
            if impl_modules is not None and impl_type.__module__ not in impl_modules:
                continue
            loc = _get_wrapper_location(impl_type)
            if loc is not None:
                yield impl_type, loc

    if hasattr(bound, "__forward_arg__"):
        forward_str = bound.__forward_arg__  # type: ignore
        matches = list(_iter_matching_name(forward_str))
        if matches:
            _, (wrapper_target_module, wrapper_name) = matches[0]
            if wrapper_target_module == target_module:
                return f'"{wrapper_name}"'
            return f'"{wrapper_target_module}.{wrapper_name}"'
        return f'"{forward_str}"'

    if isinstance(bound, str):
        matches = list(_iter_matching_name(bound))
        if matches:
            _, (wrapper_target_module, wrapper_name) = matches[0]
            if wrapper_target_module == target_module:
                return wrapper_name
            return f"{wrapper_target_module}.{wrapper_name}"
        return f'"{bound}"'

    if isinstance(bound, type):
        loc = _get_wrapper_location(bound)
        if loc is not None:
            wrapper_target_module, wrapper_name = loc
            if wrapper_target_module == target_module:
                return f'"{wrapper_name}"'
            return f'"{wrapper_target_module}.{wrapper_name}"'
        if bound.__module__ == "builtins":
            return bound.__name__
        return f"{bound.__module__}.{bound.__name__}"

    return repr(bound)


def typevar_specs_from_collected(
    module_typevars: dict[str, typing.TypeVar | typing.ParamSpec],
    known_impl_types: frozenset[type],
    target_module: str,
    *,
    impl_modules: frozenset[str] | None = None,
) -> tuple[TypeVarSpecIR, ...]:
    specs: list[TypeVarSpecIR] = []
    for name in sorted(module_typevars.keys()):
        tv = module_typevars[name]
        if isinstance(tv, typing.ParamSpec):
            specs.append(
                TypeVarSpecIR(
                    name=name,
                    is_paramspec=True,
                    constraint_parts=(),
                    bound_value=None,
                    covariant=False,
                    contravariant=False,
                    bound_translation_ir=None,
                )
            )
            continue

        constraint_parts: list[str] = []
        if hasattr(tv, "__constraints__") and tv.__constraints__:
            for constraint in tv.__constraints__:
                if isinstance(constraint, type):
                    loc = _get_wrapper_location(constraint)
                    if loc is not None:
                        wrapper_target_module, wrapper_name = loc
                        if wrapper_target_module == target_module:
                            constraint_parts.append(wrapper_name)
                        else:
                            constraint_parts.append(f"{wrapper_target_module}.{wrapper_name}")
                    else:
                        constraint_parts.append(
                            constraint.__name__
                            if constraint.__module__ == "builtins"
                            else f"{constraint.__module__}.{constraint.__name__}"
                        )
                else:
                    constraint_parts.append(repr(constraint))

        bound_value: str | None = None
        if hasattr(tv, "__bound__") and tv.__bound__ is not None:
            bound_value = translate_typevar_bound(
                tv.__bound__, known_impl_types, target_module, impl_modules=impl_modules
            )

        bound_translation_ir: TypeTransformerIR | None = None
        impl_ref = resolve_typevar_bound_to_wrapped_impl(tv, known_impl_types, impl_modules)
        if impl_ref is not None:
            loc = _get_wrapper_location_from_ref(impl_ref, known_impl_types)
            if loc is not None:
                bound_translation_ir = WrappedClassTypeIR(impl_ref, WrapperRef(*loc))

        specs.append(
            TypeVarSpecIR(
                name=name,
                is_paramspec=False,
                constraint_parts=tuple(constraint_parts),
                bound_value=bound_value,
                covariant=bool(getattr(tv, "__covariant__", False)),
                contravariant=bool(getattr(tv, "__contravariant__", False)),
                bound_translation_ir=bound_translation_ir,
            )
        )
    return tuple(specs)


def _get_wrapper_location_from_ref(
    impl_ref,
    known_impl_types: frozenset[type],
) -> tuple[str, str] | None:
    """Look up wrapper location for an ImplQualifiedRef by finding the matching type."""
    for t in known_impl_types:
        if t.__module__ == impl_ref.module and t.__qualname__ == impl_ref.qualname:
            return _get_wrapper_location(t)
    return None


def typevar_definition_lines(specs: tuple[TypeVarSpecIR, ...]) -> list[str]:
    lines: list[str] = []
    for spec in specs:
        if spec.is_paramspec:
            lines.append(f'{spec.name} = typing.ParamSpec("{spec.name}")')
            continue
        args: list[str] = [f'"{spec.name}"']
        for part in spec.constraint_parts:
            args.append(part)
        if spec.bound_value is not None:
            args.append(f"bound={spec.bound_value}")
        if spec.covariant:
            args.append("covariant=True")
        if spec.contravariant:
            args.append("contravariant=True")
        lines.append(f"{spec.name} = typing.TypeVar({', '.join(args)})")
    return lines
