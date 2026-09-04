"""Component registry: registrations keyed by ``(kind, name, version)`` (Section 15.1).

Duplicate ``(kind, name, version)`` registration is rejected. The registry stores no mutable
component instances, only classes plus immutable metadata; instances are constructed later,
explicitly, from resolved configuration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from inventory_optimizer.exceptions import RegistrationError


class ComponentKind(StrEnum):
    PROBLEM_FAMILY = "problem_family"
    CONSTRAINT = "constraint"
    OBJECTIVE = "objective"
    SOLVER_BACKEND = "solver_backend"


@dataclass(frozen=True, slots=True)
class ComponentRegistration:
    kind: ComponentKind
    name: str
    version: str
    metadata: Mapping[str, Any]
    component_class: type


class Registry:
    """A registration table. ``default_registry`` below is the process-wide instance decorators
    use unless a test passes its own isolated ``Registry`` (Section 15.1)."""

    def __init__(self) -> None:
        self._registrations: dict[tuple[ComponentKind, str, str], ComponentRegistration] = {}

    def register(
        self,
        kind: ComponentKind,
        name: str,
        version: str,
        component_class: type,
        **metadata: Any,
    ) -> ComponentRegistration:
        key = (kind, name, version)
        if key in self._registrations:
            raise RegistrationError(
                f"duplicate registration for {kind.value} {name!r} version {version!r}"
            )
        registration = ComponentRegistration(
            kind=kind,
            name=name,
            version=version,
            metadata=dict(metadata),
            component_class=component_class,
        )
        self._registrations[key] = registration
        return registration

    def get(self, kind: ComponentKind, name: str, version: str) -> ComponentRegistration:
        try:
            return self._registrations[(kind, name, version)]
        except KeyError as exc:
            raise RegistrationError(
                f"no registration for {kind.value} {name!r} version {version!r}"
            ) from exc

    def manifest(self) -> tuple[ComponentRegistration, ...]:
        """Expose every registration for audit and documentation (Section 15.1)."""
        return tuple(self._registrations.values())


default_registry = Registry()
