"""Section 22.11's deterministic multi-period settlement projection, end to end
(specs/0010-multi-period-settlement/spec.md AC-004, AC-005). No `EXAMPLES.md` worked case exists
for any multi-period scenario -- this fixture is hand-constructed and reasoned through in
`plan.md`'s "Worked fixture sketch — Phase 1", the same approach `specs/0006`-`0009` all used for
their own golden cases.

One inventory (`INV-1`, 100 lendable shares, `price_usd=10.0`), one route (`RT-A`, solved to fill
its full 100 shares at period 0, `fee_rate=0.02`, `revenue_share=1.0`, `variable_cost_rate=0.0`,
`recall_notice_days=1`), `act_360`/`planning_horizon_days=1`, `daily_discount_rate=0.0`.
`planning_periods = (effective_date + 1 day, effective_date + 3 days)`; `known_future_events`
contains one `RECALL` (`quantity_shares=40`, 3 days' notice -- satisfying `recall_notice_days=1`)
landing in period 2, not period 1.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from inventory_optimizer.domain.enums import SolverStatus, TradeEventType
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.scenarios import TradeEvent
from inventory_optimizer.facade import InventoryOptimizer
from inventory_optimizer.settlement.project import project_multi_period

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)


def _request(inventory_factory, route_factory, demand_factory) -> OptimizationRequest:
    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    route = route_factory(
        "RT-A", "DG-A", fee_rate=0.02, maximum_quantity_shares=100.0, recall_notice_days=1,
    )
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02, reference_quantity_shares=100.0)
    recall = TradeEvent(
        event_id="RECALL-1",
        event_type=TradeEventType.RECALL,
        trade_date=_EFFECTIVE_DATE,
        effective_date=_EFFECTIVE_DATE + timedelta(days=3),
        settlement_date=_EFFECTIVE_DATE + timedelta(days=3),
        quantity_shares=40.0,
        route_id="RT-A",
        source="fixture",
        source_version="v1",
    )
    return OptimizationRequest(
        request_id="REQ-MP",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
        planning_periods=(
            _EFFECTIVE_DATE + timedelta(days=1),
            _EFFECTIVE_DATE + timedelta(days=3),
        ),
        known_future_events=(recall,),
    )


def test_recall_lands_in_its_own_period_not_earlier(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-004."""
    request = _request(inventory_factory, route_factory, demand_factory)
    optimizer = InventoryOptimizer(config=default_config)
    result = optimizer.optimize(request)
    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    assert result.allocations[0].post_quantity_shares == pytest.approx(100.0)

    projection = project_multi_period(request, result, default_config)

    assert projection.mode == "projected"
    assert len(projection.balances) == 3  # one per period, one inventory record each

    period0, period1, period2 = projection.balances
    assert period0.period_date == _EFFECTIVE_DATE
    assert period0.on_loan_shares == pytest.approx(100.0)
    assert period0.available_to_lend_shares == pytest.approx(0.0)

    assert period1.period_date == _EFFECTIVE_DATE + timedelta(days=1)
    assert period1.on_loan_shares == pytest.approx(100.0)  # no event lands in (eff, +1]
    assert period1.available_to_lend_shares == pytest.approx(0.0)

    assert period2.period_date == _EFFECTIVE_DATE + timedelta(days=3)
    assert period2.on_loan_shares == pytest.approx(60.0)  # 100 - 40 recall
    assert period2.available_to_lend_shares == pytest.approx(40.0)
    assert period2.total_lendable_shares == pytest.approx(100.0)  # recall never removes supply


def test_period_economics_matches_hand_formula(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-005: each period's day_count_fraction is the gap from the *previous* period boundary
    (period 0 uses the config's own planning_horizon_days, matching result.economics), not a fixed
    constant -- period 2 spans 2 days (effective_date+1 -> effective_date+3)."""
    request = _request(inventory_factory, route_factory, demand_factory)
    optimizer = InventoryOptimizer(config=default_config)
    result = optimizer.optimize(request)

    projection = project_multi_period(request, result, default_config)

    period0, period1, period2 = projection.economics
    tau = 1.0 / 360.0  # act_360, planning_horizon_days=1

    assert period0.day_count_fraction == pytest.approx(tau)
    assert period0.undiscounted_net_revenue_usd == pytest.approx(10.0 * tau * 0.02 * 100.0)
    assert period0.discount_factor == pytest.approx(1.0)  # daily_discount_rate=0.0

    assert period1.day_count_fraction == pytest.approx(tau)  # 1-day gap
    assert period1.undiscounted_net_revenue_usd == pytest.approx(10.0 * tau * 0.02 * 100.0)

    assert period2.day_count_fraction == pytest.approx(2.0 * tau)  # 2-day gap
    assert period2.undiscounted_net_revenue_usd == pytest.approx(10.0 * (2.0 * tau) * 0.02 * 60.0)

    expected_total = (
        period0.discounted_net_revenue_usd
        + period1.discounted_net_revenue_usd
        + period2.discounted_net_revenue_usd
    )
    assert projection.total_discounted_net_revenue_usd == pytest.approx(expected_total)


def test_invariant_violation_raises_not_silently_clipped(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC per NFR-004: a known future event that would violate scenarios.apply's own existing
    invariants (a sell exceeding remaining lendable shares) raises ScenarioApplicationError rather
    than being silently clipped -- reusing apply_events' existing behavior unchanged."""
    from inventory_optimizer.exceptions import ScenarioApplicationError

    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    route = route_factory(
        "RT-A", "DG-A", fee_rate=0.02, maximum_quantity_shares=100.0, recall_notice_days=0,
    )
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02, reference_quantity_shares=100.0)
    impossible_sell = TradeEvent(
        event_id="SELL-HUGE",
        event_type=TradeEventType.SELL,
        trade_date=_EFFECTIVE_DATE,
        effective_date=_EFFECTIVE_DATE + timedelta(days=1),
        settlement_date=_EFFECTIVE_DATE + timedelta(days=1),
        quantity_shares=10_000.0,
        inventory_id="INV-1",
        source="fixture",
        source_version="v1",
    )
    request = OptimizationRequest(
        request_id="REQ-MP-IMPOSSIBLE",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
        planning_periods=(_EFFECTIVE_DATE + timedelta(days=1),),
        known_future_events=(impossible_sell,),
    )
    optimizer = InventoryOptimizer(config=default_config)
    result = optimizer.optimize(request)

    with pytest.raises(ScenarioApplicationError):
        project_multi_period(request, result, default_config)
