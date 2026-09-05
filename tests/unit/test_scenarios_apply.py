"""``apply_scenario`` unit tests (T13-T14; Section 13.2-13.3; specs/0004-scenario-engine/)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from inventory_optimizer.domain.enums import TradeEventType
from inventory_optimizer.domain.scenarios import DemandShock, RateShock, Scenario, TradeEvent
from inventory_optimizer.exceptions import ScenarioApplicationError
from inventory_optimizer.scenarios.apply import apply_scenario
from inventory_optimizer.validation.reconciliation import check_on_loan_reconciliation


def _sell(
    event_id: str, quantity: float, effective_date, *, inventory_id: str = "INV-1"
) -> TradeEvent:
    return TradeEvent(
        event_id=event_id,
        event_type=TradeEventType.SELL,
        trade_date=effective_date,
        effective_date=effective_date,
        settlement_date=effective_date,
        quantity_shares=quantity,
        inventory_id=inventory_id,
        source="fixture",
        source_version="v1",
    )


def test_apply_scenario_never_mutates_baseline(e1_request) -> None:
    """NFR-001 / SCN-001."""
    before = e1_request.model_dump_json()
    scenario = Scenario(
        scenario_id="S1",
        name="sale",
        trade_events=(_sell("SELL-1", 10.0, e1_request.effective_date),),
    )

    apply_scenario(e1_request, scenario)

    assert e1_request.model_dump_json() == before


def test_event_after_effective_date_is_not_applied(e1_request) -> None:
    """Section 13.2: only events effective by the request's effective_date alter state."""
    future_event = _sell("SELL-FUTURE", 10.0, e1_request.effective_date + timedelta(days=1))
    scenario = Scenario(scenario_id="S-FUTURE", name="future sale", trade_events=(future_event,))

    scenario_request, warnings = apply_scenario(e1_request, scenario)

    original_inventory = e1_request.inventory[0]
    scenario_inventory = scenario_request.inventory[0]
    assert scenario_inventory.total_lendable_shares == original_inventory.total_lendable_shares
    assert warnings == ()


def test_conflicting_return_events_are_rejected(e1_request) -> None:
    """AC-005 (REQ-003)."""
    make_return = lambda event_id: TradeEvent(  # noqa: E731
        event_id=event_id,
        event_type=TradeEventType.RETURN,
        trade_date=e1_request.effective_date,
        effective_date=e1_request.effective_date,
        settlement_date=e1_request.effective_date,
        quantity_shares=5.0,
        route_id="RT-A",
        source="fixture",
        source_version="v1",
    )
    scenario = Scenario(
        scenario_id="S-CONFLICT",
        name="conflicting returns",
        trade_events=(make_return("RETURN-1"), make_return("RETURN-2")),
    )

    with pytest.raises(ScenarioApplicationError):
        apply_scenario(e1_request, scenario)


def test_oversized_sell_is_rejected(e1_request) -> None:
    """AC-006 (REQ-004)."""
    huge_sell = _sell("SELL-HUGE", 10_000.0, e1_request.effective_date)
    scenario = Scenario(scenario_id="S-HUGE", name="impossible sale", trade_events=(huge_sell,))

    with pytest.raises(ScenarioApplicationError):
        apply_scenario(e1_request, scenario)


def test_return_reduces_route_and_keeps_on_loan_reconciled(e1_request) -> None:
    return_event = TradeEvent(
        event_id="RETURN-1",
        event_type=TradeEventType.RETURN,
        trade_date=e1_request.effective_date,
        effective_date=e1_request.effective_date,
        settlement_date=e1_request.effective_date,
        quantity_shares=5.0,
        route_id="RT-A",
        source="fixture",
        source_version="v1",
    )
    # RT-A starts at 0 current_quantity_shares in e1_request; give it a nonzero baseline first.
    routes = tuple(
        r.model_copy(update={"current_quantity_shares": 10.0}) if r.route_id == "RT-A" else r
        for r in e1_request.routes
    )
    inventory = e1_request.inventory[0].model_copy(
        update={"on_loan_shares": 10.0, "available_to_lend_shares": 90.0}
    )
    request = e1_request.model_copy(update={"routes": routes, "inventory": (inventory,)})
    scenario = Scenario(scenario_id="S-RETURN", name="return", trade_events=(return_event,))

    scenario_request, warnings = apply_scenario(request, scenario)

    scenario_route = next(r for r in scenario_request.routes if r.route_id == "RT-A")
    assert scenario_route.current_quantity_shares == pytest.approx(5.0)
    assert warnings == ()
    assert check_on_loan_reconciliation(scenario_request) == ()


def test_new_loan_marks_route_eligible(e1_request) -> None:
    ineligible_routes = tuple(
        r.model_copy(update={"eligible": False}) if r.route_id == "RT-B" else r
        for r in e1_request.routes
    )
    request = e1_request.model_copy(update={"routes": ineligible_routes})
    new_loan = TradeEvent(
        event_id="NEWLOAN-1",
        event_type=TradeEventType.NEW_LOAN,
        trade_date=request.effective_date,
        effective_date=request.effective_date,
        settlement_date=request.effective_date,
        quantity_shares=50.0,
        route_id="RT-B",
        source="fixture",
        source_version="v1",
    )
    scenario = Scenario(
        scenario_id="S-NEWLOAN", name="activate candidate", trade_events=(new_loan,)
    )

    scenario_request, _ = apply_scenario(request, scenario)

    scenario_route = next(r for r in scenario_request.routes if r.route_id == "RT-B")
    assert scenario_route.eligible is True


def test_rate_shock_overrides_route_fee(e1_request) -> None:
    shock = RateShock(
        shock_id="SHOCK-1",
        route_id="RT-A",
        new_fee_rate=0.10,
        source="fixture",
        source_version="v1",
    )
    scenario = Scenario(scenario_id="S-RATE", name="rate shock", rate_shocks=(shock,))

    scenario_request, _ = apply_scenario(e1_request, scenario)

    scenario_route = next(r for r in scenario_request.routes if r.route_id == "RT-A")
    assert scenario_route.fee_rate == pytest.approx(0.10)


def test_demand_shock_overrides_reference_quantity(e1_request) -> None:
    shock = DemandShock(
        shock_id="DSHOCK-1",
        demand_group_id="DG-A",
        reference_quantity_shares=10.0,
        source="fixture",
        source_version="v1",
    )
    scenario = Scenario(scenario_id="S-DEMAND", name="demand shock", demand_shocks=(shock,))

    scenario_request, _ = apply_scenario(e1_request, scenario)

    scenario_demand = next(d for d in scenario_request.demand if d.demand_group_id == "DG-A")
    assert scenario_demand.reference_quantity_shares == pytest.approx(10.0)
    # Untouched fields keep their baseline value.
    baseline_demand = next(d for d in e1_request.demand if d.demand_group_id == "DG-A")
    assert scenario_demand.reference_fee_rate == baseline_demand.reference_fee_rate
