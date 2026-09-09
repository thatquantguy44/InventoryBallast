"""Joint multi-period LP (Phase 2 / Design A; specs/0010-multi-period-settlement/; Section 22.11).

Replicates every existing baseline LP component's exact mathematical structure once per planning
period, linked by a per-period transition identity -- see ``plan.md``'s "Phase 2 details (Design A
-- joint multi-period LP)" for the full derivation this module implements.

**Plain functions, not registered ``@constraint_component`` classes** (``plan.md``'s Architecture
section): the existing ``ConstraintComponent`` protocol's ``contribute(self, context: BuildContext,
builder: SparseBuilder)`` has no period parameter, and every existing component hardcodes an
unsuffixed ``VariableKey("q", route.route_id)`` -- reusing them unchanged for one shared,
period-spanning ``SparseBuilder`` would collide period 0's ``q`` with period 5's ``q`` under the
same key. The six row-building functions below mirror
``components/constraints/inventory_balance.py``, ``utilization.py``, ``demand.py``, and
``counterparty.py`` formula-for-formula against period-suffixed ``VariableKey``s instead.

``_period_bound_adjustments`` (REQ-010) is Design A's own, distinct-from-``scenarios.apply.
apply_events`` event handling: a route's quantity at every period ``t >= 1`` is a free decision
variable (``q_{j,t}``), not a fixed number, so a ``RECALL``/``RETURN`` cannot "force" a reduction
the way ``apply_events`` computes one -- it can only tighten the bound ``q_{j,t}`` must respect.
See ``plan.md``'s "Design A's own event handling" and its recorded RETURN bound-formula reading.

This module builds only the row families themselves (REQ-009) plus the exogenous per-period bound
snapshot they read from (REQ-010) -- ``compile_multi_period_lp``/``solve_multi_period`` (REQ-012,
tying these together with the period-indexed variable index and the discounted objective) land in
a later task (T-010); nothing here is wired into ``facade.py`` or ``InventoryOptimizer.optimize()``
by design (Phase 1's own ``settlement.project.project_multi_period`` depends on ``optimize()``
staying unaware of ``planning_periods`` -- see ``plan.md``'s "A separate entry point").
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from inventory_optimizer.domain.enums import TradeEventType
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.policies import CounterpartyLimit, UtilizationPolicy
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import ScenarioApplicationError
from inventory_optimizer.formulation.context import group_by
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder
from inventory_optimizer.scenarios.apply import select_effective_events

# Three-digit zero-padding (the same lexicographic-order convention
# ``formulation.context.tier_scope_id`` uses for specs/0009's tier index) only sorts correctly up
# to 1000 distinct values; period 0 plus up to 999 planning periods fits exactly.
MAX_PLANNING_PERIODS = 999


def period_scope_id(scope_id: str, period: int) -> str:
    """The period-suffixed ``VariableKey``/row scope id convention (``plan.md``'s own:
    ``f"{route.route_id}@{t:03d}"``), zero-padded to three digits so lexicographic sort order
    (Section 16.5) matches numeric period order -- analogous to
    ``formulation.context.tier_scope_id``, a distinct implementation for a distinct separator
    rather than a literal reuse (docs/handoff.md's T-008 resume note)."""
    if not 0 <= period <= MAX_PLANNING_PERIODS:
        raise ValueError(
            f"multi-period LP supports at most {MAX_PLANNING_PERIODS} planning periods beyond "
            f"period 0 (period {period!r} out of range) -- three-digit zero-padding would no "
            "longer sort lexicographically in numeric order (Section 16.5)"
        )
    return f"{scope_id}@{period:03d}"


@dataclass(frozen=True, slots=True)
class PeriodBounds:
    """One period's exogenous, event-adjusted bounds (REQ-010) -- Design A's own construction,
    distinct from Phase 1's ``apply_events`` (see this module's own docstring). ``total_lendable_
    shares`` is what the six row-building functions below actually consume (``reserved_shares``/
    ``committed_out_shares`` are never touched by any event type, so row-building functions read
    those directly off the baseline ``request.inventory``). ``maximum_quantity_shares``/
    ``eligible`` are this helper's full REQ-010 output (every event type's effect on a route's
    bounds, per ``plan.md``'s event-to-bound-adjustment table) but are not yet consumed anywhere in
    this module -- T-010's own period-indexed variable-bounds setter (the multi-period analogue of
    ``formulation.compiler_support.set_route_bounds``) is their intended, not-yet-built consumer.
    ``hard_minimum_quantity_shares`` is never adjusted by any event (``plan.md``'s recorded RETURN
    reading), so it stays period-invariant and is read directly off ``request.routes`` wherever
    needed."""

    total_lendable_shares: Mapping[str, float]
    maximum_quantity_shares: Mapping[str, float]
    eligible: Mapping[str, bool]


def _period_bound_adjustments(
    request: OptimizationRequest, boundaries: Sequence[date]
) -> tuple[PeriodBounds, ...]:
    """REQ-010. Walks ``request.known_future_events`` through the same ``scenarios.apply.
    select_effective_events`` timing/ordering rule Phase 1's ``apply_events`` uses, but --unlike
    ``apply_events``-- accumulates bound values for a free decision variable rather than mutating a
    fully-determined snapshot. Returns one ``PeriodBounds`` per entry in ``boundaries`` (period 0
    first, with no event yet applied -- exactly today's baseline, unchanged).

    RETURN and RECALL share one code path: ``plan.md``'s recorded resolution reads RETURN's
    "hard_minimum" wording as "floored at," not "also reduced," so both use the identical formula
    ``_apply_trade_event``'s RECALL branch already uses: ``max(maximum_quantity_shares -
    quantity_shares, hard_minimum_quantity_shares)``.
    """
    total_lendable: dict[str, float] = {
        inventory.inventory_id: inventory.total_lendable_shares for inventory in request.inventory
    }
    maximum_quantity: dict[str, float] = {
        route.route_id: route.maximum_quantity_shares for route in request.routes
    }
    eligible: dict[str, bool] = {route.route_id: route.eligible for route in request.routes}
    inventory_by_id = {inventory.inventory_id: inventory for inventory in request.inventory}
    routes_by_id = {route.route_id: route for route in request.routes}

    def _snapshot() -> PeriodBounds:
        return PeriodBounds(
            total_lendable_shares=dict(total_lendable),
            maximum_quantity_shares=dict(maximum_quantity),
            eligible=dict(eligible),
        )

    snapshots: list[PeriodBounds] = [_snapshot()]
    for previous_boundary, this_boundary in itertools.pairwise(boundaries):
        events = select_effective_events(
            request.known_future_events, after=previous_boundary, on_or_before=this_boundary
        )
        for event in events:
            if event.event_type in (TradeEventType.BUY, TradeEventType.TRANSFER_IN):
                assert event.inventory_id is not None
                if (
                    event.event_type is TradeEventType.TRANSFER_IN
                    and not inventory_by_id[event.inventory_id].eligible
                ):
                    continue  # destination pool ineligible; transfer has no effect (Section 13.1)
                total_lendable[event.inventory_id] += event.quantity_shares
            elif event.event_type in (TradeEventType.SELL, TradeEventType.TRANSFER_OUT):
                assert event.inventory_id is not None
                new_total = total_lendable[event.inventory_id] - event.quantity_shares
                if new_total < 0.0:
                    raise ScenarioApplicationError(
                        f"known future event {event.event_id!r} would drive inventory "
                        f"{event.inventory_id!r}'s total_lendable_shares negative "
                        f"({new_total!r}) by {this_boundary!r}; cannot sell/transfer out more "
                        "than is held"
                    )
                total_lendable[event.inventory_id] = new_total
            elif event.event_type is TradeEventType.NEW_LOAN:
                assert event.route_id is not None
                eligible[event.route_id] = True
                maximum_quantity[event.route_id] = max(
                    maximum_quantity[event.route_id], event.quantity_shares
                )
            elif event.event_type in (TradeEventType.RETURN, TradeEventType.RECALL):
                assert event.route_id is not None
                route = routes_by_id[event.route_id]
                maximum_quantity[event.route_id] = max(
                    maximum_quantity[event.route_id] - event.quantity_shares,
                    route.hard_minimum_quantity_shares,
                )
        snapshots.append(_snapshot())
    return tuple(snapshots)


@dataclass(frozen=True, slots=True)
class RouteGroupings:
    """The period-invariant groupings every row-building function needs -- route ids don't change
    per period, only certain bound *values* do (``PeriodBounds``), so this is computed once per
    multi-period compile via ``formulation.context.group_by`` (promoted from private for exactly
    this reuse), not once per period."""

    inventory_by_id: Mapping[str, SecurityInventory]
    routes_by_inventory: Mapping[str, tuple[LoanRoute, ...]]
    routes_by_demand_group: Mapping[str, tuple[LoanRoute, ...]]
    routes_by_borrower: Mapping[str, tuple[LoanRoute, ...]]


def _build_route_groupings(request: OptimizationRequest) -> RouteGroupings:
    return RouteGroupings(
        inventory_by_id={inventory.inventory_id: inventory for inventory in request.inventory},
        routes_by_inventory=group_by(request.routes, key=lambda route: route.inventory_id),
        routes_by_demand_group=group_by(request.routes, key=lambda route: route.demand_group_id),
        routes_by_borrower=group_by(request.routes, key=lambda route: route.borrower_id),
    )


@dataclass(frozen=True, slots=True)
class MultiPeriodContext:
    """Everything the period-indexed row-building functions below need for one planning period
    ``t``. ``request``, ``groupings``, and ``demand_caps`` are period-invariant (route ids don't
    change per period, only certain bound *values* do -- computed once, shared by every period, not
    rebuilt per period). ``demand_caps`` holds only the effective cap in shares (``D_g``, constant
    across ``t`` -- ``plan.md``'s Non-Goal), not the full ``elasticity.EvaluatedDemand`` the
    single-period ``BuildContext`` carries -- nothing here needs the rest of that shape."""

    request: OptimizationRequest
    period: int
    bounds: PeriodBounds
    groupings: RouteGroupings
    demand_caps: Mapping[str, float]

    @property
    def inventory_by_id(self) -> Mapping[str, SecurityInventory]:
        return self.groupings.inventory_by_id

    @property
    def routes_by_inventory(self) -> Mapping[str, tuple[LoanRoute, ...]]:
        return self.groupings.routes_by_inventory

    @property
    def routes_by_demand_group(self) -> Mapping[str, tuple[LoanRoute, ...]]:
        return self.groupings.routes_by_demand_group

    @property
    def routes_by_borrower(self) -> Mapping[str, tuple[LoanRoute, ...]]:
        return self.groupings.routes_by_borrower


def _policy_applies(policy: UtilizationPolicy, inventory: SecurityInventory) -> bool:
    if (
        policy.inventory_pool_id is not None
        and policy.inventory_pool_id != inventory.inventory_pool_id
    ):
        return False
    if policy.security_id is not None and policy.security_id != inventory.security_id:
        return False
    return True


def _in_scope(limit: CounterpartyLimit, route: LoanRoute, context: MultiPeriodContext) -> bool:
    if limit.security_id is not None and limit.security_id != route.security_id:
        return False
    if limit.inventory_pool_id is not None:
        inventory = context.inventory_by_id[route.inventory_id]
        if limit.inventory_pool_id != inventory.inventory_pool_id:
            return False
    return True


def inventory_balance(context: MultiPeriodContext, builder: SparseBuilder) -> None:
    """``sum(q_j,t for j in J(i)) + a_i,t = L_i,t - R_i - C_i`` -- mirrors
    ``components.constraints.inventory_balance.InventoryBalanceConstraint`` exactly, period 0
    byte-identical to the baseline row (``L_i,0`` is the unmodified ``request.inventory`` value)."""
    for inventory in context.request.inventory:
        total_lendable = context.bounds.total_lendable_shares[inventory.inventory_id]
        rhs = total_lendable - inventory.reserved_shares - inventory.committed_out_shares
        row = builder.add_row(
            "inventory_balance",
            period_scope_id(inventory.inventory_id, context.period),
            lower=rhs,
            upper=rhs,
        )
        for route in context.routes_by_inventory.get(inventory.inventory_id, ()):
            builder.add_row_coefficient(
                row, VariableKey("q", period_scope_id(route.route_id, context.period)), 1.0
            )
        builder.add_row_coefficient(
            row, VariableKey("a", period_scope_id(inventory.inventory_id, context.period)), 1.0
        )


def transition_identity(context: MultiPeriodContext, builder: SparseBuilder) -> None:
    """``q_j,t - q_j,t-1 = inc_j,t - dec_j,t``, with ``q_j,-1 := route.current_quantity_shares`` --
    period 0's row is exactly ``components.constraints.inventory_balance.
    TransitionIdentityConstraint``'s baseline row (a fixed RHS, no ``q_{t-1}`` term); every later
    period moves the previous period's ``q`` onto the LHS instead, since it is itself a decision
    variable, not a constant."""
    period = context.period
    for route in context.request.routes:
        row = builder.add_row(
            "transition_identity",
            period_scope_id(route.route_id, period),
            lower=0.0 if period > 0 else route.current_quantity_shares,
            upper=0.0 if period > 0 else route.current_quantity_shares,
        )
        builder.add_row_coefficient(
            row, VariableKey("q", period_scope_id(route.route_id, period)), 1.0
        )
        builder.add_row_coefficient(
            row, VariableKey("inc", period_scope_id(route.route_id, period)), -1.0
        )
        builder.add_row_coefficient(
            row, VariableKey("dec", period_scope_id(route.route_id, period)), 1.0
        )
        if period > 0:
            builder.add_row_coefficient(
                row, VariableKey("q", period_scope_id(route.route_id, period - 1)), -1.0
            )


def demand_cap(context: MultiPeriodContext, builder: SparseBuilder) -> None:
    """``sum(q_j,t for j in J(g)) <= D_g`` -- mirrors ``components.constraints.demand.
    DemandCapConstraint``, ``D_g`` constant across ``t`` (``plan.md``'s Non-Goal). No fee-tier skip
    is needed here (unlike the baseline component): REQ-012 already fails a tiered request closed
    before this module is ever reached (``formulation.compiler_support.
    multi_period_conflict_issues``)."""
    for forecast in context.request.demand:
        routes = context.routes_by_demand_group.get(forecast.demand_group_id, ())
        if not routes:
            continue
        cap = context.demand_caps[forecast.demand_group_id]
        row = builder.add_row(
            "demand_cap",
            period_scope_id(forecast.demand_group_id, context.period),
            lower=-math.inf,
            upper=cap,
        )
        for route in routes:
            builder.add_row_coefficient(
                row, VariableKey("q", period_scope_id(route.route_id, context.period)), 1.0
            )


def utilization_cap(context: MultiPeriodContext, builder: SparseBuilder) -> None:
    """``u_min_i * L_i,t <= O_i,t <= u_max_i * L_i,t`` -- mirrors ``components.constraints.
    utilization.UtilizationCapConstraint``, against period ``t``'s own event-adjusted
    ``total_lendable_shares``."""
    for inventory in context.request.inventory:
        routes = context.routes_by_inventory.get(inventory.inventory_id, ())
        total_lendable = context.bounds.total_lendable_shares[inventory.inventory_id]
        for policy in context.request.utilization_policies:
            if not _policy_applies(policy, inventory):
                continue
            if policy.maximum_utilization is not None:
                row = builder.add_row(
                    "utilization_max",
                    period_scope_id(f"{inventory.inventory_id}:{policy.policy_id}", context.period),
                    lower=-math.inf,
                    upper=policy.maximum_utilization * total_lendable,
                )
                for route in routes:
                    builder.add_row_coefficient(
                        row, VariableKey("q", period_scope_id(route.route_id, context.period)), 1.0
                    )
            if policy.minimum_utilization is not None:
                row = builder.add_row(
                    "utilization_min",
                    period_scope_id(f"{inventory.inventory_id}:{policy.policy_id}", context.period),
                    lower=policy.minimum_utilization * total_lendable,
                    upper=math.inf,
                )
                for route in routes:
                    builder.add_row_coefficient(
                        row, VariableKey("q", period_scope_id(route.route_id, context.period)), 1.0
                    )


def reserve_buffer(context: MultiPeriodContext, builder: SparseBuilder) -> None:
    """``a_i,t >= absolute_buffer_i`` and/or ``a_i,t >= buffer_fraction_i * L_i,t`` -- mirrors
    ``components.constraints.utilization.ReserveBufferConstraint``, a tightened lower bound on
    ``a_i,t`` rather than an extra row, against period ``t``'s own ``total_lendable_shares``."""
    for inventory in context.request.inventory:
        total_lendable = context.bounds.total_lendable_shares[inventory.inventory_id]
        buffer = 0.0
        for policy in context.request.utilization_policies:
            if not _policy_applies(policy, inventory):
                continue
            buffer = max(
                buffer,
                policy.reserve_buffer_shares,
                policy.reserve_buffer_fraction * total_lendable,
            )
        if buffer > 0.0:
            builder.set_variable_bounds(
                VariableKey("a", period_scope_id(inventory.inventory_id, context.period)),
                lower=buffer,
                upper=math.inf,
            )


def counterparty_limit(context: MultiPeriodContext, builder: SparseBuilder) -> None:
    """``sum(P_i(j) * q_j,t for j in J(b)) <= K_b`` (notional) and/or ``sum(q_j,t for j in J(b)) <=
    K_b`` (quantity) -- mirrors ``components.constraints.counterparty.
    CounterpartyLimitConstraint``."""
    for limit in context.request.counterparty_limits:
        routes = [
            route
            for route in context.routes_by_borrower.get(limit.borrower_id, ())
            if _in_scope(limit, route, context)
        ]
        if not routes:
            continue

        if limit.maximum_quantity_shares is not None:
            row = builder.add_row(
                "counterparty_quantity",
                period_scope_id(limit.limit_id, context.period),
                lower=-math.inf,
                upper=limit.maximum_quantity_shares,
            )
            for route in routes:
                builder.add_row_coefficient(
                    row, VariableKey("q", period_scope_id(route.route_id, context.period)), 1.0
                )

        if limit.maximum_notional_usd is not None:
            row = builder.add_row(
                "counterparty_notional",
                period_scope_id(limit.limit_id, context.period),
                lower=-math.inf,
                upper=limit.maximum_notional_usd,
            )
            for route in routes:
                price = context.inventory_by_id[route.inventory_id].price_usd
                builder.add_row_coefficient(
                    row, VariableKey("q", period_scope_id(route.route_id, context.period)), price
                )


__all__ = [
    "MAX_PLANNING_PERIODS",
    "MultiPeriodContext",
    "PeriodBounds",
    "RouteGroupings",
    "counterparty_limit",
    "demand_cap",
    "inventory_balance",
    "period_scope_id",
    "reserve_buffer",
    "transition_identity",
    "utilization_cap",
]
