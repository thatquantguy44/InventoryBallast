"""Input invariants and independent result checks (Section 7.1).

Must not own objective policy. ``validate_request`` aggregates every detectable issue across
field-level construction (handled by the frozen domain contracts), request-level freshness, and
cross-record reconciliation, matching Section 9.8's "one InputValidationError, not one field at a
time" requirement.
"""

from __future__ import annotations

from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import InputValidationError, ValidationIssue
from inventory_optimizer.validation.input_validation import (
    DEFAULT_MAX_STALENESS_HOURS,
    check_freshness,
)
from inventory_optimizer.validation.reconciliation import reconcile
from inventory_optimizer.validation.solution_verifier import (
    DEFAULT_TOLERANCE,
    VerificationReport,
    verify_solution,
)


def validate_request(
    request: OptimizationRequest,
    *,
    max_staleness_hours: float = DEFAULT_MAX_STALENESS_HOURS,
) -> tuple[ValidationIssue, ...]:
    """Return every detectable Section 9.8 issue for an already-constructed request."""
    return check_freshness(request, max_staleness_hours=max_staleness_hours) + reconcile(request)


def raise_if_invalid(
    request: OptimizationRequest,
    *,
    max_staleness_hours: float = DEFAULT_MAX_STALENESS_HOURS,
) -> None:
    issues = validate_request(request, max_staleness_hours=max_staleness_hours)
    if issues:
        raise InputValidationError(issues)


__all__ = [
    "DEFAULT_TOLERANCE",
    "InputValidationError",
    "ValidationIssue",
    "VerificationReport",
    "raise_if_invalid",
    "validate_request",
    "verify_solution",
]
