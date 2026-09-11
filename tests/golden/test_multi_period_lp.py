"""Section 22.11's joint multi-period LP (Design A), end to end
(specs/0010-multi-period-settlement/spec.md AC-006). No `EXAMPLES.md` worked case exists for any
multi-period scenario -- this fixture is hand-constructed and reasoned through here, the same
approach `specs/0006`-`0009` all used for their own golden cases.

One inventory (`INV-1`, 100 lendable shares, `price_usd=10.0`), one route (`RT-A`, starting
*unlent* -- `current_quantity_shares=0.0`, unlike Phase 1's own fixture which starts fully lent --
`fee_rate=0.02`, `revenue_share=1.0`, `variable_cost_rate=0.0`, `recall_notice_days=1`),
`act_360`/`planning_horizon_days=1`, `daily_discount_rate=0.0`. `planning_periods = (effective_date
+ 1 day,)`; `known_future_events` contains one `RECALL` of the *entire* position (100 shares),
`trade_date=effective_date`, `effective_date=effective_date + 1 day` -- exactly `recall_notice_days`
of notice, satisfying REQ-003.

Because the recall is total, period 1's `q` bound is forced to exactly `[0, 0]`
(`compute_period_bound_adjustments`'s own `RECALL` formula: `max(100 - 100, hard_minimum=0) == 0`)
regardless of what period 0 lends -- so whatever is lent at period 0 must be entirely unwound
(`dec_1 == q_0`) by period 1. This is a deliberate, simpler substitute for `plan.md`'s own fixture
sketch text (which names `increase_cost_usd_per_share` as the cost that matters): with a *total*
recall, period 1's own quantity never depends on period 0's chosen value in a way `increase_cost`
could influence (there is no room to *increase* into after a total recall), so the real coupling in
this exact fixture is `decrease_cost_usd_per_share` -- the cost of the forced period-1 unwind. This
substitution is recorded here rather than silently reproducing `plan.md`'s prose as if it were the
literal mechanism.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from inventory_optimizer.domain.enums import SolverStatus, TradeEventType
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.scenarios import TradeEvent
from inventory_optimizer.formulation.multi_period import solve_multi_period

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)
_TAU = 1.0 / 360.0  # act_360, planning_horizon_days=1
_FEE_REVENUE_PER_SHARE = 10.0 * _TAU * 0.02  # price * tau * (fee_rate * revenue_share)


def _request(inventory_factory, route_factory, demand_factory, *, decrease_cost: float):
    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    route = route_factory(
        "RT-A", "DG-A", fee_rate=0.02, maximum_quantity_shares=100.0,
        current_quantity_shares=0.0, recall_notice_days=1,
        decrease_cost_usd_per_share=decrease_cost,
    )
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02, reference_quantity_shares=100.0)
    recall = TradeEvent(
        event_id="RECALL-1",
        event_type=TradeEventType.RECALL,
        trade_date=_EFFECTIVE_DATE,
        effective_date=_EFFECTIVE_DATE + timedelta(days=1),
        settlement_date=_EFFECTIVE_DATE + timedelta(days=1),
        quantity_shares=100.0,
        route_id="RT-A",
        source="fixture",
        source_version="v1",
    )
    return OptimizationRequest(
        request_id="REQ-MPLP",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
        planning_periods=(_EFFECTIVE_DATE + timedelta(days=1),),
        known_future_events=(recall,),
    )


def test_cheap_unwind_matches_the_single_period_optimum(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """Control case: with `decrease_cost_usd_per_share` below the per-share revenue rate, the
    forced unwind is cheaper than the period-0 revenue it would forgo, so the joint LP lends the
    full amount anyway -- the same answer a single-period-only optimizer would give. Establishes
    that the reduction in the next test comes specifically from `decrease_cost`, not some other
    effect of the joint compiler."""
    request = _request(
        inventory_factory, route_factory, demand_factory,
        decrease_cost=_FEE_REVENUE_PER_SHARE / 2.0,
    )
    projection = solve_multi_period(request, default_config)

    assert projection.status is SolverStatus.OPTIMAL
    assert projection.balances[0].on_loan_shares == pytest.approx(100.0)
    assert projection.balances[1].on_loan_shares == pytest.approx(0.0)


def test_known_future_recall_reduces_period_zero_allocation(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-006. `decrease_cost_usd_per_share` set well above the per-share revenue rate
    (`_FEE_REVENUE_PER_SHARE`), so unwinding a lent share at period 1 costs strictly more than
    lending it earned at period 0 -- the joint LP should lend nothing at period 0, since any
    amount lent would have to be entirely, and expensively, unwound one period later. A
    single-period-only optimizer (blind to the future recall) would lend the full 100."""
    decrease_cost = _FEE_REVENUE_PER_SHARE * 100.0  # two orders of magnitude above breakeven
    request = _request(
        inventory_factory, route_factory, demand_factory, decrease_cost=decrease_cost
    )

    projection = solve_multi_period(request, default_config)

    assert projection.status is SolverStatus.OPTIMAL
    period0, period1 = projection.balances
    single_period_optimum = 100.0
    assert period0.on_loan_shares < single_period_optimum
    assert period0.on_loan_shares == pytest.approx(0.0)  # hand-computed: breakeven is far exceeded
    assert period1.on_loan_shares == pytest.approx(0.0)  # the recall forces this regardless

    # The horizon's total discounted objective exceeds what period-0-only optimization (lend the
    # full 100, blind to the future recall) plus the recall's own forced consequence would have
    # produced -- hand-computed, never read back from a second solve.
    naive_period0_revenue = _FEE_REVENUE_PER_SHARE * single_period_optimum
    naive_forced_unwind_cost = decrease_cost * single_period_optimum
    naive_total = naive_period0_revenue - naive_forced_unwind_cost
    assert projection.total_discounted_net_revenue_usd == pytest.approx(0.0)
    assert projection.total_discounted_net_revenue_usd > naive_total
    assert naive_total < 0.0  # the naive plan is a genuine loss here, not just a smaller gain
