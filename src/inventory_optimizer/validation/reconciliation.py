"""Cross-record reconciliation invariants that need sibling records from one request.

Implements the checkable subset of Section 9.8 for the Phase 0A vertical (invariants 1, 6, 8, 9,
10). Schedule/collateral/agency/prime invariants (13-21) are added with their owning subsystems.
Each function returns every issue it finds; callers aggregate rather than short-circuit.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import ValidationIssue

BALANCE_TOLERANCE_SHARES = 1e-6


def _duplicates(ids: list[str]) -> list[str]:
    counts = Counter(ids)
    return sorted(id_ for id_, n in counts.items() if n > 1)


def check_unique_ids(request: OptimizationRequest) -> tuple[ValidationIssue, ...]:
    """Invariant 1 (uniqueness half): IDs are unique in their declared scope."""
    issues: list[ValidationIssue] = []
    scopes = (
        ("inventory", "inventory_id", [i.inventory_id for i in request.inventory]),
        ("routes", "route_id", [r.route_id for r in request.routes]),
        ("demand", "demand_group_id", [d.demand_group_id for d in request.demand]),
        (
            "counterparty_limits",
            "limit_id",
            [c.limit_id for c in request.counterparty_limits],
        ),
        (
            "utilization_policies",
            "policy_id",
            [p.policy_id for p in request.utilization_policies],
        ),
    )
    for location, field, ids in scopes:
        for dup in _duplicates(ids):
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_ID",
                    message=f"duplicate {field} {dup!r} in {location}",
                    location=f"{location}[{field}={dup!r}]",
                )
            )
    return tuple(issues)


def check_foreign_keys(request: OptimizationRequest) -> tuple[ValidationIssue, ...]:
    """Invariant 1 (resolution half) and invariant 10: eligible route inventory/security IDs
    agree."""
    issues: list[ValidationIssue] = []
    inventory_by_id = {i.inventory_id: i for i in request.inventory}
    demand_by_id = {d.demand_group_id: d for d in request.demand}

    for idx, route in enumerate(request.routes):
        location = f"routes[{idx}]"
        inventory = inventory_by_id.get(route.inventory_id)
        if inventory is None:
            issues.append(
                ValidationIssue(
                    code="UNRESOLVED_FOREIGN_KEY",
                    message=f"route.inventory_id {route.inventory_id!r} does not resolve",
                    location=f"{location}.inventory_id",
                )
            )
        elif inventory.security_id != route.security_id:
            issues.append(
                ValidationIssue(
                    code="INVENTORY_SECURITY_MISMATCH",
                    message=(
                        f"route.security_id {route.security_id!r} does not match "
                        f"inventory.security_id {inventory.security_id!r}"
                    ),
                    location=f"{location}.security_id",
                )
            )
        if route.demand_group_id not in demand_by_id:
            issues.append(
                ValidationIssue(
                    code="UNRESOLVED_FOREIGN_KEY",
                    message=f"route.demand_group_id {route.demand_group_id!r} does not resolve",
                    location=f"{location}.demand_group_id",
                )
            )
    return tuple(issues)


def check_on_loan_reconciliation(request: OptimizationRequest) -> tuple[ValidationIssue, ...]:
    """Invariant 6: sum of current route quantities equals inventory.on_loan_shares per record."""
    issues: list[ValidationIssue] = []
    current_by_inventory: dict[str, float] = defaultdict(float)
    for route in request.routes:
        current_by_inventory[route.inventory_id] += route.current_quantity_shares

    for idx, inventory in enumerate(request.inventory):
        routed = current_by_inventory.get(inventory.inventory_id, 0.0)
        if abs(routed - inventory.on_loan_shares) > BALANCE_TOLERANCE_SHARES:
            issues.append(
                ValidationIssue(
                    code="ON_LOAN_RECONCILIATION_FAILED",
                    message=(
                        f"sum of route current_quantity_shares ({routed!r}) does not equal "
                        f"inventory.on_loan_shares ({inventory.on_loan_shares!r}) for "
                        f"inventory_id {inventory.inventory_id!r}"
                    ),
                    location=f"inventory[{idx}].on_loan_shares",
                )
            )
    return tuple(issues)


def check_term_and_recall_timing(request: OptimizationRequest) -> tuple[ValidationIssue, ...]:
    """Invariant 8: term/recall rules are consistent with the effective date."""
    issues: list[ValidationIssue] = []
    for idx, route in enumerate(request.routes):
        if route.term_end_date is not None and route.term_end_date < request.effective_date:
            issues.append(
                ValidationIssue(
                    code="TERM_ALREADY_EXPIRED",
                    message=(
                        f"term_end_date {route.term_end_date!r} precedes "
                        f"effective_date {request.effective_date!r}"
                    ),
                    location=f"routes[{idx}].term_end_date",
                )
            )
    return tuple(issues)


def check_demand_group_consistency(request: OptimizationRequest) -> tuple[ValidationIssue, ...]:
    """Invariant 9: demand groups do not mix security or borrower IDs."""
    issues: list[ValidationIssue] = []
    demand_by_id = {d.demand_group_id: d for d in request.demand}
    for idx, route in enumerate(request.routes):
        forecast = demand_by_id.get(route.demand_group_id)
        if forecast is None:
            continue  # reported by check_foreign_keys
        if forecast.security_id != route.security_id:
            issues.append(
                ValidationIssue(
                    code="DEMAND_GROUP_SECURITY_MISMATCH",
                    message=(
                        f"route.security_id {route.security_id!r} does not match demand group "
                        f"{route.demand_group_id!r} security_id {forecast.security_id!r}"
                    ),
                    location=f"routes[{idx}].demand_group_id",
                )
            )
        if forecast.borrower_id != route.borrower_id:
            issues.append(
                ValidationIssue(
                    code="DEMAND_GROUP_BORROWER_MISMATCH",
                    message=(
                        f"route.borrower_id {route.borrower_id!r} does not match demand group "
                        f"{route.demand_group_id!r} borrower_id {forecast.borrower_id!r}"
                    ),
                    location=f"routes[{idx}].demand_group_id",
                )
            )
    return tuple(issues)


def reconcile(request: OptimizationRequest) -> tuple[ValidationIssue, ...]:
    """Run every reconciliation check and aggregate issues."""
    return (
        check_unique_ids(request)
        + check_foreign_keys(request)
        + check_on_loan_reconciliation(request)
        + check_term_and_recall_timing(request)
        + check_demand_group_consistency(request)
    )
