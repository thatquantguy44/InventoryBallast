"""Freshness and other single-request structural checks (Section 9.8 invariant 2).

Field-level type/range/unit invariants (3, 4, 7, 11) are enforced by the Pydantic domain contracts
themselves at construction time; this module covers request-level checks that need the request's
``as_of`` alongside sibling records.
"""

from __future__ import annotations

from datetime import timedelta

from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import ValidationIssue

DEFAULT_MAX_STALENESS_HOURS = 24.0


def check_freshness(
    request: OptimizationRequest, *, max_staleness_hours: float = DEFAULT_MAX_STALENESS_HOURS
) -> tuple[ValidationIssue, ...]:
    """Invariant 2: required timestamps meet the freshness/common-as-of policy."""
    issues: list[ValidationIssue] = []
    max_age = timedelta(hours=max_staleness_hours)

    for idx, inventory in enumerate(request.inventory):
        age = request.as_of - inventory.as_of
        if age > max_age or age < timedelta(0):
            issues.append(
                ValidationIssue(
                    code="STALE_OR_FUTURE_AS_OF",
                    message=(
                        f"inventory.as_of {inventory.as_of!r} is {age} away from "
                        f"request.as_of {request.as_of!r}; max staleness is {max_age}"
                    ),
                    location=f"inventory[{idx}].as_of",
                )
            )

    for idx, demand in enumerate(request.demand):
        age = request.as_of - demand.as_of
        if age > max_age or age < timedelta(0):
            issues.append(
                ValidationIssue(
                    code="STALE_OR_FUTURE_AS_OF",
                    message=(
                        f"demand.as_of {demand.as_of!r} is {age} away from "
                        f"request.as_of {request.as_of!r}; max staleness is {max_age}"
                    ),
                    location=f"demand[{idx}].as_of",
                )
            )
    return tuple(issues)
