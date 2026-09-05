"""EXAMPLES.md E2 -- Fee Elasticity Shock, reproduced as a scenario (T13-T14; specs/0004-scenario-
engine/spec.md AC-001/AC-002).

E2 is, on inspection, a ``RateShock`` scenario: raising a route's fee from 2.00% to 3.00% with
``epsilon=0.5`` reduces the effective demand cap from 80 to 65.3197264742 shares -- reproduced here
through the real scenario-apply -> re-optimize pipeline, with **no changes to** ``reporting/`` or
``formulation/`` at all (``ELASTICITY_REDUCED_DEMAND`` falls out of the already-existing T06/T11
machinery once the route's fee_rate changes before compilation).
"""

from __future__ import annotations

import pytest

from inventory_optimizer.domain.enums import ReasonCode
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.scenarios import RateShock, Scenario
from inventory_optimizer.facade import InventoryOptimizer
from inventory_optimizer.scenarios.runner import run_scenario

_EXPECTED_SHOCKED_DEMAND_CAP = 65.3197264742


@pytest.fixture
def e2_request(inventory_factory, route_factory, demand_factory) -> OptimizationRequest:
    from datetime import UTC, date, datetime

    as_of = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    inventory = inventory_factory(
        total_lendable_shares=100.0, on_loan_shares=0.0, available_to_lend_shares=100.0
    )
    route = route_factory(
        "RT-A", "DG-A", fee_rate=0.02, current_quantity_shares=0.0, maximum_quantity_shares=100.0
    )
    demand = demand_factory(
        "DG-A", "BORROWER-RT-A", fee_rate=0.02, reference_quantity_shares=80.0, elasticity=0.5
    )
    return OptimizationRequest(
        request_id="REQ-E2",
        as_of=as_of,
        effective_date=date(2026, 9, 3),
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )


def test_rate_shock_reproduces_e2_demand_cap_and_reason_code(e2_request, default_config) -> None:
    """AC-001."""
    optimizer = InventoryOptimizer(config=default_config)
    baseline_result = optimizer.optimize(e2_request)
    shock = RateShock(
        shock_id="SHOCK-1",
        route_id="RT-A",
        new_fee_rate=0.03,
        source="fixture",
        source_version="v1",
    )
    scenario = Scenario(scenario_id="E2-FEE-SHOCK", name="Fee shock to 3%", rate_shocks=(shock,))

    comparison = run_scenario(e2_request, baseline_result, scenario, optimizer)

    assert baseline_result.demand[0].effective_cap_shares == pytest.approx(80.0)
    # Re-solve once more (outside run_scenario) purely to inspect the scenario allocation's
    # reason codes -- ScenarioComparison itself doesn't carry per-route ReasonCode detail beyond
    # TRADE_REDUCED_SUPPLY.
    from inventory_optimizer.scenarios.apply import apply_scenario

    scenario_request, _ = apply_scenario(e2_request, scenario)
    scenario_result = optimizer.optimize(scenario_request)

    assert scenario_result.demand[0].effective_cap_shares == pytest.approx(
        _EXPECTED_SHOCKED_DEMAND_CAP, rel=1e-9
    )
    assert scenario_result.allocations[0].post_quantity_shares == pytest.approx(
        _EXPECTED_SHOCKED_DEMAND_CAP, rel=1e-9
    )
    assert ReasonCode.ELASTICITY_REDUCED_DEMAND in scenario_result.allocations[0].reason_codes
    assert comparison.objective_delta_usd == pytest.approx(
        scenario_result.economics.total_value_usd - baseline_result.economics.total_value_usd
    )


def test_baseline_request_unchanged_after_scenario(e2_request, default_config) -> None:
    """AC-002 (SCN-001)."""
    before = e2_request.model_dump_json()
    optimizer = InventoryOptimizer(config=default_config)
    baseline_result = optimizer.optimize(e2_request)
    shock = RateShock(
        shock_id="SHOCK-1",
        route_id="RT-A",
        new_fee_rate=0.03,
        source="fixture",
        source_version="v1",
    )
    scenario = Scenario(scenario_id="E2-FEE-SHOCK", name="Fee shock to 3%", rate_shocks=(shock,))

    run_scenario(e2_request, baseline_result, scenario, optimizer)

    assert e2_request.model_dump_json() == before
