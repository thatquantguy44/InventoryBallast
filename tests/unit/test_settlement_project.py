"""``settlement.project`` unit tests (specs/0010-multi-period-settlement/): boundary/ordering
behavior for ``select_effective_events``, formulation-independence (AC-006... actually AC covering
REQ-008's formulation-independence for period 0), and ``mode``/``disclosure`` (AC-008).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from inventory_optimizer.domain.enums import TradeEventType
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.scenarios import TradeEvent
from inventory_optimizer.facade import InventoryOptimizer
from inventory_optimizer.scenarios.apply import select_effective_events
from inventory_optimizer.settlement.project import project_multi_period

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)


def _buy(event_id: str, effective_date: date) -> TradeEvent:
    return TradeEvent(
        event_id=event_id,
        event_type=TradeEventType.BUY,
        trade_date=effective_date,
        effective_date=effective_date,
        settlement_date=effective_date,
        quantity_shares=1.0,
        inventory_id="INV-1",
        source="fixture",
        source_version="v1",
    )


def test_event_exactly_on_a_boundary_lands_in_that_period_not_the_next() -> None:
    events = [_buy("B1", _EFFECTIVE_DATE + timedelta(days=1))]
    period_one = select_effective_events(
        events, after=_EFFECTIVE_DATE, on_or_before=_EFFECTIVE_DATE + timedelta(days=1)
    )
    period_two = select_effective_events(
        events,
        after=_EFFECTIVE_DATE + timedelta(days=1),
        on_or_before=_EFFECTIVE_DATE + timedelta(days=3),
    )
    assert [e.event_id for e in period_one] == ["B1"]
    assert period_two == []


def test_event_beyond_the_horizon_is_never_selected() -> None:
    """Mirrors Section 13.2's own "later events ... do not affect" wording, one step further: an
    event beyond the last planning_periods boundary is retained on the request but never applied
    by any period's own window."""
    events = [_buy("B-FAR", _EFFECTIVE_DATE + timedelta(days=30))]
    selected = select_effective_events(
        events, after=_EFFECTIVE_DATE, on_or_before=_EFFECTIVE_DATE + timedelta(days=3)
    )
    assert selected == []


def test_projection_is_formulation_independent_for_mip(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """Period 0 solved via compile_mip (an all_or_none route) -- the projection reads only
    OptimizationResult's already-solved fields, never the compiler."""
    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    route = route_factory(
        "RT-A", "DG-A", fee_rate=0.02, maximum_quantity_shares=50.0, all_or_none=True,
    )
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02, reference_quantity_shares=50.0)
    request = OptimizationRequest(
        request_id="REQ-MP-MIP",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
        planning_periods=(_EFFECTIVE_DATE + timedelta(days=1),),
    )
    optimizer = InventoryOptimizer(config=default_config)
    result = optimizer.optimize(request)
    assert result.allocations[0].post_quantity_shares == pytest.approx(50.0)  # MIP filled fully

    projection = project_multi_period(request, result, default_config)

    assert projection.mode == "projected"
    assert projection.balances[0].on_loan_shares == pytest.approx(50.0)


def test_mode_is_projected(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-008."""
    inventory = inventory_factory()
    route = route_factory("RT-A", "DG-A", fee_rate=0.02)
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02)
    request = OptimizationRequest(
        request_id="REQ-MP-MODE",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
        planning_periods=(_EFFECTIVE_DATE + timedelta(days=1),),
    )
    optimizer = InventoryOptimizer(config=default_config)
    result = optimizer.optimize(request)

    projection = project_multi_period(request, result, default_config)

    assert projection.mode == "projected"
    assert "not a re-optimized plan" in projection.disclosure


def test_project_multi_period_rejects_empty_planning_periods(e1_request, default_config) -> None:
    optimizer = InventoryOptimizer(config=default_config)
    result = optimizer.optimize(e1_request)

    with pytest.raises(ValueError, match="planning_periods"):
        project_multi_period(e1_request, result, default_config)
