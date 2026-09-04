"""Registration decorators for problem families, constraints, objectives, and solver backends
(Section 15).

Registration occurs at module import; component *instances* are always constructed later from
resolved configuration. Decorators never execute solver or I/O work (Section 15.1).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

from inventory_optimizer.components.registry import ComponentKind, Registry, default_registry
from inventory_optimizer.domain.enums import Capability, Formulation
from inventory_optimizer.exceptions import RegistrationError

T = TypeVar("T", bound=type)


def _require_attrs(cls: type, attrs: Iterable[str], role: str) -> None:
    missing = [attr for attr in attrs if not hasattr(cls, attr)]
    if missing:
        raise RegistrationError(
            f"{cls.__name__} is missing required {role} attribute(s): {missing}"
        )


def problem_family(
    *,
    name: str,
    version: str,
    supported_formulations: Iterable[Formulation],
    registry: Registry = default_registry,
) -> Callable[[T], T]:
    def decorator(cls: T) -> T:
        _require_attrs(cls, ("request_type", "result_type"), "problem-family")
        registry.register(
            ComponentKind.PROBLEM_FAMILY,
            name,
            version,
            cls,
            supported_formulations=frozenset(supported_formulations),
        )
        return cls

    return decorator


def constraint_component(
    *,
    name: str,
    version: str,
    formulations: Iterable[Formulation],
    hard: bool,
    registry: Registry = default_registry,
) -> Callable[[T], T]:
    def decorator(cls: T) -> T:
        _require_attrs(cls, ("validate", "contribute"), "constraint-component")
        registry.register(
            ComponentKind.CONSTRAINT,
            name,
            version,
            cls,
            formulations=frozenset(formulations),
            hard=hard,
        )
        return cls

    return decorator


def objective_component(
    *,
    name: str,
    version: str,
    formulations: Iterable[Formulation],
    registry: Registry = default_registry,
) -> Callable[[T], T]:
    def decorator(cls: T) -> T:
        _require_attrs(cls, ("validate", "contribute", "attribute"), "objective-component")
        registry.register(
            ComponentKind.OBJECTIVE,
            name,
            version,
            cls,
            formulations=frozenset(formulations),
        )
        return cls

    return decorator


def solver_backend(
    *,
    name: str,
    capabilities: Iterable[Capability],
    version: str = "1",
    registry: Registry = default_registry,
) -> Callable[[T], T]:
    def decorator(cls: T) -> T:
        _require_attrs(cls, ("solve",), "solver-backend")
        registry.register(
            ComponentKind.SOLVER_BACKEND,
            name,
            version,
            cls,
            capabilities=frozenset(capabilities),
        )
        return cls

    return decorator
