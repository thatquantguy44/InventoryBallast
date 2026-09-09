"""Cross-record reconciliation invariants that need sibling records from one request.

Implements the checkable subset of Section 9.8 for the Phase 0A vertical (invariants 1, 6, 8, 9,
10). Schedule/collateral/agency/prime invariants (13-21) are added with their owning subsystems.
Each function returns every issue it finds; callers aggregate rather than short-circuit.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from inventory_optimizer.domain.enums import TradeEventType
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


def check_demand_group_fee_consistency(request: OptimizationRequest) -> tuple[ValidationIssue, ...]:
    """Section 12.2: "All routes in one LP demand group must share the evaluated borrower fee ...
    If route rates imply genuinely different borrower price choices, use distinct demand groups or
    the discrete pricing MIP." Routes sharing a ``demand_group_id`` must therefore share a
    ``fee_rate``; lender ``revenue_share`` may still differ."""
    issues: list[ValidationIssue] = []
    fee_by_group: dict[str, tuple[int, float]] = {}
    for idx, route in enumerate(request.routes):
        first = fee_by_group.get(route.demand_group_id)
        if first is None:
            fee_by_group[route.demand_group_id] = (idx, route.fee_rate)
        elif abs(first[1] - route.fee_rate) > BALANCE_TOLERANCE_SHARES:
            issues.append(
                ValidationIssue(
                    code="DEMAND_GROUP_FEE_INCONSISTENT",
                    message=(
                        f"route.fee_rate {route.fee_rate!r} differs from routes[{first[0]}]."
                        f"fee_rate {first[1]!r} in the same demand group "
                        f"{route.demand_group_id!r}; use distinct demand groups or the discrete "
                        "pricing MIP for genuinely different borrower prices"
                    ),
                    location=f"routes[{idx}].fee_rate",
                )
            )
    return tuple(issues)


def check_recall_notice_sufficiency(request: OptimizationRequest) -> tuple[ValidationIssue, ...]:
    """specs/0010-multi-period-settlement/ REQ-003: a known future ``RECALL`` must give the
    referenced route at least its own ``recall_notice_days`` of notice -- measured from when the
    recall was issued (``trade_date``) to when it takes effect (``effective_date``), not from
    ``request.effective_date`` (which would measure "how far in the future this is from today,"
    not "how much notice the borrower actually got"). Applies uniformly regardless of which
    downstream design (the deterministic projection or the joint multi-period LP) later consumes
    ``known_future_events`` -- an operationally impossible recall is rejected here, once, rather
    than silently honored by either."""
    routes_by_id = {route.route_id: route for route in request.routes}
    issues: list[ValidationIssue] = []
    for idx, event in enumerate(request.known_future_events):
        if event.event_type is not TradeEventType.RECALL:
            continue
        route = routes_by_id.get(event.route_id)
        if route is None:
            continue  # unresolved route_id is already reported by check_foreign_keys
        notice_days = (event.effective_date - event.trade_date).days
        if notice_days < route.recall_notice_days:
            issues.append(
                ValidationIssue(
                    code="RECALL_NOTICE_INSUFFICIENT",
                    message=(
                        f"known_future_events[{idx}] (event_id={event.event_id!r}) gives "
                        f"{notice_days} day(s) notice, less than route {event.route_id!r}'s "
                        f"recall_notice_days ({route.recall_notice_days!r})"
                    ),
                    location=f"known_future_events[{idx}].effective_date",
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
        + check_demand_group_fee_consistency(request)
        + check_recall_notice_sufficiency(request)
    )
