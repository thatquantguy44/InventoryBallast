"""01_SPEC.md Section 24.5 -- Existing-loan churn case (specs/0005-test-hardening/spec.md
AC-011).

Supply (100 shares) is fully allocated to a 1.00% current route. A 1.10% candidate route appears,
competing for the same inventory record. With transition costs greater than the horizon fee
uplift (0.10% * price * tau per share), the current route remains unchanged. With zero transition
costs, inventory moves to the higher-rate route, subject to its demand maximum. Section 18.2's
objective attribution (T11) must reconstruct both outcomes exactly -- ``verification.passed``
stands in for "the objective attribution must explain both outcomes" (no separate assertion
mechanism is needed; T11's attribution already hard-fails on any reconstruction mismatch).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from inventory_optimizer.domain.enums import SolverStatus
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.facade import InventoryOptimizer

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)


def _churn_request(
    inventory_factory, route_factory, demand_factory, *, transition_cost_usd_per_share: float
) -> OptimizationRequest:
    inventory = inventory_factory(
        total_lendable_shares=100.0, on_loan_shares=100.0, available_to_lend_shares=0.0
    )
    current_route = route_factory(
        "RT-CURRENT",
        "DG-CURRENT",
        fee_rate=0.010,
        borrower_id="BORROWER-CURRENT",
        current_quantity_shares=100.0,
        maximum_quantity_shares=100.0,
        decrease_cost_usd_per_share=transition_cost_usd_per_share,
    )
    candidate_route = route_factory(
        "RT-CANDIDATE",
        "DG-CANDIDATE",
        fee_rate=0.011,
        borrower_id="BORROWER-CANDIDATE",
        current_quantity_shares=0.0,
        maximum_quantity_shares=100.0,
        increase_cost_usd_per_share=transition_cost_usd_per_share,
    )
    demand_current = demand_factory(
        "DG-CURRENT", "BORROWER-CURRENT", fee_rate=0.010, reference_quantity_shares=100.0
    )
    demand_candidate = demand_factory(
        "DG-CANDIDATE", "BORROWER-CANDIDATE", fee_rate=0.011, reference_quantity_shares=100.0
    )
    return OptimizationRequest(
        request_id="REQ-CHURN",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(current_route, candidate_route),
        demand=(demand_current, demand_candidate),
    )


def test_high_transition_cost_keeps_current_route_unchanged(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """Uplift per share is 10.0 * (1/360) * 0.001 ~= 0.0000278; a 0.001/share transition cost on
    both sides (0.002 combined) swamps it, so churning is never worthwhile."""
    request = _churn_request(
        inventory_factory, route_factory, demand_factory, transition_cost_usd_per_share=0.001
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    allocations = {a.route_id: a.post_quantity_shares for a in result.allocations}
    assert allocations["RT-CURRENT"] == pytest.approx(100.0)
    assert allocations["RT-CANDIDATE"] == pytest.approx(0.0)


def test_zero_transition_cost_churns_to_higher_rate_route(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    request = _churn_request(
        inventory_factory, route_factory, demand_factory, transition_cost_usd_per_share=0.0
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    allocations = {a.route_id: a.post_quantity_shares for a in result.allocations}
    assert allocations["RT-CURRENT"] == pytest.approx(0.0)
    assert allocations["RT-CANDIDATE"] == pytest.approx(100.0)
