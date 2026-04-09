"""Serialize typing.TypeVar / ParamSpec into primitive specs and source lines."""

from __future__ import annotations

import typing

from .ir import TypeVarSpecIR


def translate_typevar_bound(
    bound: type | str,
    synchronized_types: dict[type, tuple[str, str]],
    target_module: str,
    *,
    impl_modules: frozenset[str] | None = None,
) -> str:
    def _iter_matching_name(name: str):
        for impl_type, pair in synchronized_types.items():
            if impl_type.__name__ != name:
                continue
            if impl_modules is not None and impl_type.__module__ not in impl_modules:
                continue
            yield impl_type, pair

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
        if bound in synchronized_types:
            wrapper_target_module, wrapper_name = synchronized_types[bound]
            if wrapper_target_module == target_module:
                return f'"{wrapper_name}"'
            return f'"{wrapper_target_module}.{wrapper_name}"'
        if bound.__module__ == "builtins":
            return bound.__name__
        return f"{bound.__module__}.{bound.__name__}"

    return repr(bound)


def typevar_specs_from_collected(
    module_typevars: dict[str, typing.TypeVar | typing.ParamSpec],
    synchronized_types: dict[type, tuple[str, str]],
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
                )
            )
            continue

        constraint_parts: list[str] = []
        if hasattr(tv, "__constraints__") and tv.__constraints__:
            for constraint in tv.__constraints__:
                if isinstance(constraint, type):
                    if constraint in synchronized_types:
                        wrapper_target_module, wrapper_name = synchronized_types[constraint]
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
                tv.__bound__, synchronized_types, target_module, impl_modules=impl_modules
            )

        specs.append(
            TypeVarSpecIR(
                name=name,
                is_paramspec=False,
                constraint_parts=tuple(constraint_parts),
                bound_value=bound_value,
                covariant=bool(getattr(tv, "__covariant__", False)),
                contravariant=bool(getattr(tv, "__contravariant__", False)),
            )
        )
    return tuple(specs)


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
