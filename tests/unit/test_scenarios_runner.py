"""``run_scenario``/``run_scenarios``/``run_stress_test`` tests (T13-T14; SCN-003;
specs/0004-scenario-engine/).
"""

from __future__ import annotations

from inventory_optimizer.domain.enums import TradeEventType
from inventory_optimizer.domain.scenarios import RateShock, Scenario, TradeEvent
from inventory_optimizer.facade import InventoryOptimizer
from inventory_optimizer.scenarios.runner import run_scenario, run_scenarios, run_stress_test


def _sell_scenario(scenario_id: str, request, quantity: float) -> Scenario:
    event = TradeEvent(
        event_id=f"{scenario_id}-SELL",
        event_type=TradeEventType.SELL,
        trade_date=request.effective_date,
        effective_date=request.effective_date,
        settlement_date=request.effective_date,
        quantity_shares=quantity,
        inventory_id="INV-1",
        source="fixture",
        source_version="v1",
    )
    return Scenario(scenario_id=scenario_id, name=scenario_id, trade_events=(event,))


def _rate_scenario(scenario_id: str, route_id: str, new_fee_rate: float) -> Scenario:
    shock = RateShock(
        shock_id=f"{scenario_id}-RATE",
        route_id=route_id,
        new_fee_rate=new_fee_rate,
        source="fixture",
        source_version="v1",
    )
    return Scenario(scenario_id=scenario_id, name=scenario_id, rate_shocks=(shock,))


def test_batch_matches_isolated_runs(e1_request, default_config) -> None:
    """AC-007 (SCN-003)."""
    optimizer = InventoryOptimizer(config=default_config)
    baseline_result = optimizer.optimize(e1_request)
    scenarios = [
        _sell_scenario("SALE-10", e1_request, 10.0),
        _rate_scenario("RATE-UP", "RT-A", 0.05),
    ]

    batch = run_scenarios(e1_request, baseline_result, scenarios, optimizer)
    isolated = tuple(
        run_scenario(e1_request, baseline_result, scenario, optimizer) for scenario in scenarios
    )

    def _strip_identity(comparison):
        payload = comparison.model_dump(mode="json")
        payload.pop("baseline_run_id")
        payload.pop("scenario_run_id")
        return payload

    assert [_strip_identity(c) for c in batch] == [_strip_identity(c) for c in isolated]


def test_stress_test_report_counts_and_worst_case(e1_request, default_config) -> None:
    """AC-010."""
    optimizer = InventoryOptimizer(config=default_config)
    baseline_result = optimizer.optimize(e1_request)

    # Two engineered-infeasible scenarios: a sale far larger than the inventory can bear once
    # RT-A/RT-B's hard minimums (0 by default) are raised to lock in the current book.
    huge_sale = _sell_scenario("HUGE-SALE", e1_request, 95.0)
    mild_sale = _sell_scenario("MILD-SALE", e1_request, 5.0)
    rate_up = _rate_scenario("RATE-UP", "RT-A", 0.05)
    rate_down = _rate_scenario("RATE-DOWN", "RT-A", 0.001)

    scenarios = [huge_sale, mild_sale, rate_up, rate_down]
    report = run_stress_test(e1_request, baseline_result, scenarios, optimizer)

    assert report.scenario_count == 4
    assert report.feasible_count == 4  # a large sale alone isn't infeasible without a hard minimum
    assert report.infeasible_count == 0
    # HUGE-SALE crushes total_lendable_shares to 5, the largest revenue hit of the four.
    assert report.worst_case_scenario_id == "HUGE-SALE"
    assert report.worst_case_objective_delta_usd is not None
    assert report.worst_case_objective_delta_usd < 0
    outcomes_by_id = {o.scenario_id: o for o in report.outcomes}
    assert outcomes_by_id["RATE-DOWN"].objective_delta_usd < 0
    assert outcomes_by_id["RATE-UP"].objective_delta_usd > 0
