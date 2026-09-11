"""Discounted multi-period objective (specs/0010-multi-period-settlement/ Phase 2, T-009; Design A;
Section 22.11; REQ-007, REQ-011):

    maximize  sum_t  discount_factor_t * [
        sum_j fee_revenue_coefficient(route_j, period_tau_t) * q_{j,t}
        - k+_j * inc_{j,t} - k-_j * dec_{j,t}
    ]

A plain function module, not a registered ``@objective_component`` -- the existing
``ObjectiveComponent`` protocol expects a single-period ``BuildContext``, which Phase 2 never
builds (see ``formulation.multi_period``'s own module docstring for why its constraints are plain
functions too). ``period_tau``/``period_discount_factor`` are exposed for reuse by
``formulation.multi_period``'s future result builder (T-010), which needs the same per-period
values to construct ``domain.settlement.PeriodEconomics`` for the ``mode="jointly_optimized"``
case.

Reuses ``fee_revenue.fee_revenue_coefficient``'s exact price/fee/share/cost formula unchanged
(generalized in this spec to accept an explicit ``day_count_fraction`` override) -- only ``tau``
becomes period-specific; fee rates, prices, and variable costs are held constant across the
horizon (spec.md Non-Goals).

Period 0's ``tau`` intentionally does **not** come from a boundary difference (there is no period
before ``boundaries[0]`` to difference against) -- it reuses ``config.formulation.
planning_horizon_days`` directly, the same value today's single-period objective already uses, so
period 0's own coefficient here is byte-identical to ``FeeRevenueTerm.contribute()``'s. Period 0's
discount factor is always exactly ``1.0`` (``boundaries[0] - boundaries[0] == 0`` days), matching
Phase 1's ``settlement.project._period_economics`` -- both designs report identical period-0
economics by construction, not by coincidence, since both start from the same request.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from inventory_optimizer.components.objective_terms.fee_revenue import (
    DAY_COUNT_DIVISOR,
    fee_revenue_coefficient,
)
from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a formulation.multi_period <-> here
    # import cycle: formulation.multi_period (T-010) imports contribute_multi_period_objective
    # from this module to build the joint LP's objective row, so this module cannot import
    # formulation.multi_period back at runtime.
    from inventory_optimizer.formulation.multi_period import MultiPeriodContext

_PERIOD_SEPARATOR = "@"


def _period_variable_key(kind: str, base_id: str, period_index: int) -> VariableKey:
    """A private duplicate of ``formulation.multi_period.period_variable_key`` (same formula,
    not importable here -- see the ``TYPE_CHECKING`` note above)."""
    return VariableKey(kind=kind, scope_id=f"{base_id}{_PERIOD_SEPARATOR}{period_index:03d}")


def period_tau(
    config: InventoryOptimizerConfig, boundaries: tuple[date, ...], period_index: int
) -> float:
    """The day-count fraction for period ``period_index`` -- period 0 uses today's existing
    single-period ``planning_horizon_days`` (this module's own docstring); period ``t >= 1`` is the
    gap from the previous period boundary."""
    day_divisor = DAY_COUNT_DIVISOR[config.formulation.day_count_basis]
    if period_index == 0:
        return config.formulation.planning_horizon_days / day_divisor
    return (boundaries[period_index] - boundaries[period_index - 1]).days / day_divisor


def period_discount_factor(
    config: InventoryOptimizerConfig, boundaries: tuple[date, ...], period_index: int
) -> float:
    """``(1 + daily_discount_rate) ** -(boundary_t - effective_date).days``. Always ``1.0`` at
    period 0 (``boundaries[0]`` is ``effective_date`` itself)."""
    days_since_effective = (boundaries[period_index] - boundaries[0]).days
    return (1.0 + config.multi_period.daily_discount_rate) ** -days_since_effective


def contribute_period_objective(
    context: MultiPeriodContext, builder: SparseBuilder, period_index: int
) -> None:
    tau = period_tau(context.config, context.boundaries, period_index)
    discount = period_discount_factor(context.config, context.boundaries, period_index)
    for route in context.request.routes:
        inventory = context.inventory_by_id[route.inventory_id]
        coefficient = fee_revenue_coefficient(
            route, inventory, context.config.formulation, day_count_fraction=tau
        )
        builder.add_objective_coefficient(
            _period_variable_key("q", route.route_id, period_index), discount * coefficient
        )
        builder.add_objective_coefficient(
            _period_variable_key("inc", route.route_id, period_index),
            -discount * route.increase_cost_usd_per_share,
        )
        builder.add_objective_coefficient(
            _period_variable_key("dec", route.route_id, period_index),
            -discount * route.decrease_cost_usd_per_share,
        )


def contribute_multi_period_objective(context: MultiPeriodContext, builder: SparseBuilder) -> None:
    """Every period's discounted objective contribution, period 0 through N."""
    for period_index in range(context.period_count):
        contribute_period_objective(context, builder, period_index)
