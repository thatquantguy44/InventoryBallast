"""EXAMPLES.md E3 -- Proposed Sale and Recall Feasibility (T13-T14;
specs/0004-scenario-engine/spec.md AC-003/AC-004).

"Use E1 with the utilization cap removed and treat the result as the current book": 100 lendable
shares, Route A at 80 (2.00% fee), Route B at 20 (1.00% fee), zero transition costs. A 30-share
``SELL`` drops ``total_lendable_shares`` to 70.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from inventory_optimizer.domain.enums import ReasonCode, SolverStatus, TradeEventType
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.scenarios import Scenario, TradeEvent
from inventory_optimizer.facade import InventoryOptimizer
from inventory_optimizer.scenarios.runner import run_scenario

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)


def _e3_request(
    inventory_factory, route_factory, demand_factory, *, route_a_hard_minimum: float = 0.0
) -> OptimizationRequest:
    inventory = inventory_factory(
        total_lendable_shares=100.0, on_loan_shares=100.0, available_to_lend_shares=0.0
    )
    route_a = route_factory(
        "RT-A",
        "DG-A",
        fee_rate=0.02,
        current_quantity_shares=80.0,
        hard_minimum_quantity_shares=route_a_hard_minimum,
        maximum_quantity_shares=80.0,
    )
    route_b = route_factory(
        "RT-B", "DG-B", fee_rate=0.01, current_quantity_shares=20.0, maximum_quantity_shares=20.0
    )
    demand_a = demand_factory(
        "DG-A", "BORROWER-RT-A", fee_rate=0.02, reference_quantity_shares=80.0
    )
    demand_b = demand_factory(
        "DG-B", "BORROWER-RT-B", fee_rate=0.01, reference_quantity_shares=20.0
    )
    return OptimizationRequest(
        request_id="REQ-E3",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route_a, route_b),
        demand=(demand_a, demand_b),
    )


def _sale_scenario() -> Scenario:
    sell = TradeEvent(
        event_id="SELL-1",
        event_type=TradeEventType.SELL,
        trade_date=_EFFECTIVE_DATE,
        effective_date=_EFFECTIVE_DATE,
        settlement_date=_EFFECTIVE_DATE,
        quantity_shares=30.0,
        inventory_id="INV-1",
        source="fixture",
        source_version="v1",
    )
    return Scenario(scenario_id="E3-SALE", name="Sale of 30 shares", trade_events=(sell,))


def test_feasible_sale_redistributes_allocation(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-003."""
    request = _e3_request(inventory_factory, route_factory, demand_factory)
    optimizer = InventoryOptimizer(config=default_config)
    baseline_result = optimizer.optimize(request)

    comparison = run_scenario(request, baseline_result, _sale_scenario(), optimizer)

    assert comparison.status is SolverStatus.OPTIMAL
    allocations_by_route = {a.route_id: a for a in comparison.allocations}
    assert allocations_by_route["RT-A"].scenario_quantity_shares == pytest.approx(70.0)
    assert allocations_by_route["RT-B"].scenario_quantity_shares == pytest.approx(0.0)
    assert allocations_by_route["RT-A"].delta_shares == pytest.approx(-10.0)
    assert allocations_by_route["RT-B"].delta_shares == pytest.approx(-20.0)
    assert ReasonCode.TRADE_REDUCED_SUPPLY in allocations_by_route["RT-A"].reason_codes
    assert ReasonCode.TRADE_REDUCED_SUPPLY in allocations_by_route["RT-B"].reason_codes
    assert allocations_by_route["RT-A"].estimated_revenue_delta_usd < 0
    assert comparison.balances[0].scenario_total_lendable_shares == pytest.approx(70.0)


def test_infeasible_sale_with_hard_minimum_conflict(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-004."""
    request = _e3_request(
        inventory_factory, route_factory, demand_factory, route_a_hard_minimum=80.0
    )
    optimizer = InventoryOptimizer(config=default_config)
    baseline_result = optimizer.optimize(request)

    comparison = run_scenario(request, baseline_result, _sale_scenario(), optimizer)

    assert comparison.status is SolverStatus.INFEASIBLE
    assert comparison.allocations == ()
