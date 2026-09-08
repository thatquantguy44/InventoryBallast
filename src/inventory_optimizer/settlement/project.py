"""Deterministic multi-period settlement projection (specs/0010-multi-period-settlement/ Phase 1;
Section 22.11).

``project_multi_period`` is a pure function: period 0 is the already-solved, already-independently-
verified allocation (``result.allocations``/``result.balances``, not re-derived); periods 1..N are
produced by walking that state forward through ``request.planning_periods``, reapplying the
existing, unchanged per-event-type mechanics ``scenarios.apply.apply_events`` already implements,
using only the ``known_future_events`` effective in each period (``scenarios.apply.
select_effective_events``). This is a *projection*, not a re-optimization -- period 0 is the only
period this repo's optimizer ever decided; see ``domain.settlement.MultiPeriodProjection``'s own
docstring for the ``mode="projected"`` disclosure this always carries.

Formulation-independent by construction: this module reads only ``OptimizationResult``'s already-
solved, already-verified fields, never the compiler or ``BuildContext`` that produced them -- it
works identically regardless of whether period 0 was solved via ``compile_lp``, ``compile_mip``, or
``compile_qp``.
"""

from __future__ import annotations

from datetime import date
from itertools import pairwise

from inventory_optimizer.components.objective_terms.fee_revenue import DAY_COUNT_DIVISOR
from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.results import OptimizationResult
from inventory_optimizer.domain.settlement import (
    MultiPeriodProjection,
    PeriodBalance,
    PeriodEconomics,
    disclosure_for_mode,
)
from inventory_optimizer.scenarios.apply import apply_events, select_effective_events


def _settle_period_zero(
    request: OptimizationRequest, result: OptimizationResult
) -> OptimizationRequest:
    """REQ-005: period 0's starting state is the already-solved allocation, not the pre-solve
    request -- each route's solved ``post_quantity_shares`` becomes its ``current_quantity_shares``,
    and each inventory's already-independently-verified post-solve balance becomes its own
    ``on_loan_shares``/``available_to_lend_shares``. ``total_lendable_shares``/``reserved_shares``/
    ``committed_out_shares`` are untouched -- solving never changes what is held, only how it is
    allocated."""
    if not result.verification.has_primal:
        raise ValueError(
            "cannot project a multi-period settlement from a result with no feasible primal "
            f"(request_id={request.request_id!r})"
        )
    quantity_by_route = {a.route_id: a.post_quantity_shares for a in result.allocations}
    balance_by_inventory = {b.inventory_id: b for b in result.balances}

    routes = tuple(
        route.model_copy(update={"current_quantity_shares": quantity_by_route[route.route_id]})
        for route in request.routes
    )
    inventory = tuple(
        inv.model_copy(
            update={
                "on_loan_shares": balance_by_inventory[inv.inventory_id].post_on_loan_shares,
                "available_to_lend_shares": (
                    balance_by_inventory[inv.inventory_id].post_available_shares
                ),
            }
        )
        for inv in request.inventory
    )
    return request.model_copy(update={"routes": routes, "inventory": inventory})


def _period_economics(
    state: OptimizationRequest,
    *,
    period_index: int,
    period_date: date,
    day_count_fraction: float,
    days_since_effective: int,
    daily_discount_rate: float,
) -> PeriodEconomics:
    inventory_by_id = {inv.inventory_id: inv for inv in state.inventory}
    undiscounted = 0.0
    for route in state.routes:
        inventory = inventory_by_id[route.inventory_id]
        coefficient = inventory.price_usd * day_count_fraction * (
            route.fee_rate * route.revenue_share - route.variable_cost_rate
        )
        undiscounted += coefficient * route.current_quantity_shares
    discount_factor = (1.0 + daily_discount_rate) ** -days_since_effective
    return PeriodEconomics(
        period_index=period_index,
        period_date=period_date,
        day_count_fraction=day_count_fraction,
        undiscounted_net_revenue_usd=undiscounted,
        discount_factor=discount_factor,
        discounted_net_revenue_usd=undiscounted * discount_factor,
    )


def project_multi_period(
    request: OptimizationRequest,
    result: OptimizationResult,
    config: InventoryOptimizerConfig,
) -> MultiPeriodProjection:
    """REQ-004 through REQ-008. Empty ``request.planning_periods`` is a caller error here (there is
    nothing to project) -- callers should simply not call this for an unset request."""
    if not request.planning_periods:
        raise ValueError(
            "project_multi_period requires a non-empty planning_periods "
            f"(request_id={request.request_id!r})"
        )

    day_divisor = DAY_COUNT_DIVISOR[config.formulation.day_count_basis]
    daily_rate = config.multi_period.daily_discount_rate

    settled = _settle_period_zero(request, result)
    boundaries = (request.effective_date, *request.planning_periods)
    states = [settled]
    all_warnings: list[str] = []
    for previous_boundary, this_boundary in pairwise(boundaries):
        events = select_effective_events(
            request.known_future_events, after=previous_boundary, on_or_before=this_boundary
        )
        updated, warnings = apply_events(states[-1], events)
        states.append(updated)
        all_warnings.extend(warnings)

    balances: list[PeriodBalance] = []
    economics: list[PeriodEconomics] = []
    total_discounted = 0.0
    for period_index, (state, boundary) in enumerate(zip(states, boundaries, strict=True)):
        for inventory in state.inventory:
            total_lendable = inventory.total_lendable_shares
            utilization = (
                inventory.on_loan_shares / total_lendable if total_lendable > 0.0 else 0.0
            )
            balances.append(
                PeriodBalance(
                    inventory_id=inventory.inventory_id,
                    period_index=period_index,
                    period_date=boundary,
                    total_lendable_shares=total_lendable,
                    on_loan_shares=inventory.on_loan_shares,
                    available_to_lend_shares=inventory.available_to_lend_shares,
                    utilization=utilization,
                )
            )

        if period_index == 0:
            # Period 0 is exactly today's existing single-period economics: the config's own
            # planning_horizon_days, matching result.economics precisely (not a zero-length period).
            day_count_fraction = config.formulation.planning_horizon_days / day_divisor
        else:
            day_count_fraction = (boundary - boundaries[period_index - 1]).days / day_divisor
        days_since_effective = (boundary - request.effective_date).days

        period_econ = _period_economics(
            state,
            period_index=period_index,
            period_date=boundary,
            day_count_fraction=day_count_fraction,
            days_since_effective=days_since_effective,
            daily_discount_rate=daily_rate,
        )
        economics.append(period_econ)
        total_discounted += period_econ.discounted_net_revenue_usd

    return MultiPeriodProjection(
        request_id=request.request_id,
        mode="projected",
        planning_periods=request.planning_periods,
        balances=tuple(balances),
        economics=tuple(economics),
        total_discounted_net_revenue_usd=total_discounted,
        warnings=tuple(all_warnings),
        disclosure=disclosure_for_mode("projected"),
    )
