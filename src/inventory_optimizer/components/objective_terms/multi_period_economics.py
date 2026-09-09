"""Discounted multi-period objective (Phase 2 / Design A; specs/0010-multi-period-settlement/;
Section 22.11; REQ-007, REQ-011):

    maximize  sum_t  discount_factor_t * [ sum_j fee_revenue_coefficient(route_j, period_tau_t) *
                                            q_{j,t} - k+_j * inc_{j,t} - k-_j * dec_{j,t} ]

``fee_revenue_coefficient``'s price/fee/share/cost math is reused unchanged
(``fee_revenue.fee_revenue_coefficient_for_tau``) -- only the day-count fraction it is multiplied
by becomes period-specific (fee rates/prices are held constant across the horizon, ``plan.md``'s
Non-Goals). ``k+_j``/``k-_j`` (``route.increase_cost_usd_per_share``/
``decrease_cost_usd_per_share``) are reused exactly as ``transition_cost.TransitionCostTerm`` uses
them, just discounted and period-suffixed.

A **plain function, not a registered ``@objective_component`` class** -- the same reasoning
``formulation/multi_period.py``'s own module docstring gives for its six row-building functions:
the registered ``ObjectiveComponent`` protocol has no period parameter, and every existing
objective component hardcodes an unsuffixed ``VariableKey``. This function reuses each baseline
term's *formula*, not its *code*, against period-suffixed keys instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from inventory_optimizer.components.objective_terms.fee_revenue import (
    DAY_COUNT_DIVISOR,
    fee_revenue_coefficient_for_tau,
)
from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.multi_period import MultiPeriodContext, period_scope_id
from inventory_optimizer.formulation.sparse_builder import SparseBuilder


def period_economics_factors(
    boundaries: Sequence[date], config: InventoryOptimizerConfig
) -> tuple[tuple[float, float], ...]:
    """REQ-007, REQ-011: one ``(day_count_fraction, discount_factor)`` pair per entry in
    ``boundaries`` (period 0 first). Generalizes T08's single-period ``tau``
    (``FormulationConfig.planning_horizon_days / DAY_COUNT_DIVISOR[day_count_basis]``) to a
    period-specific day count: period 0's own fraction is *exactly* that existing scalar (matching
    ``OptimizationResult.economics`` precisely, not a zero-length period); every later period's
    fraction is the gap from the *previous* period boundary, mirroring
    ``settlement.project.project_multi_period``'s own per-period economics construction (Phase 1),
    reimplemented here for Phase 2's differently-shaped caller (a free decision variable per period,
    not an already-settled snapshot) rather than shared code -- the same "related, not identical"
    reuse ``plan.md``'s "Design A's own event handling" already establishes for
    ``_period_bound_adjustments`` vs. ``apply_events``.

    ``discount_factor_t = (1 + daily_discount_rate) ** -(boundary_t - effective_date).days``, where
    ``effective_date`` is ``boundaries[0]``.
    """
    day_divisor = DAY_COUNT_DIVISOR[config.formulation.day_count_basis]
    daily_rate = config.multi_period.daily_discount_rate
    factors: list[tuple[float, float]] = []
    for period_index, boundary in enumerate(boundaries):
        if period_index == 0:
            day_count_fraction = config.formulation.planning_horizon_days / day_divisor
        else:
            day_count_fraction = (boundary - boundaries[period_index - 1]).days / day_divisor
        days_since_effective = (boundary - boundaries[0]).days
        discount_factor = (1.0 + daily_rate) ** -days_since_effective
        factors.append((day_count_fraction, discount_factor))
    return tuple(factors)


def multi_period_economics(context: MultiPeriodContext, builder: SparseBuilder) -> None:
    """REQ-011's discounted per-period fee-revenue-net-of-transition-cost term, for period
    ``context.period`` alone -- called once per period by ``formulation.multi_period.
    compile_multi_period_lp`` (T-010), the same way each of the six row-building functions is."""
    discount = context.discount_factor
    period = context.period
    for route in context.request.routes:
        inventory = context.inventory_by_id[route.inventory_id]
        fee_coefficient = fee_revenue_coefficient_for_tau(
            route, inventory, context.day_count_fraction
        )
        builder.add_objective_coefficient(
            VariableKey("q", period_scope_id(route.route_id, period)), discount * fee_coefficient
        )
        builder.add_objective_coefficient(
            VariableKey("inc", period_scope_id(route.route_id, period)),
            -discount * route.increase_cost_usd_per_share,
        )
        builder.add_objective_coefficient(
            VariableKey("dec", period_scope_id(route.route_id, period)),
            -discount * route.decrease_cost_usd_per_share,
        )


__all__ = ["multi_period_economics", "period_economics_factors"]
