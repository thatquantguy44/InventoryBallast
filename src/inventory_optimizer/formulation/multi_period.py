"""Joint multi-period LP row/bound construction (specs/0010-multi-period-settlement/ Phase 2,
T-008; Design A; Section 22.11).

Replicates every baseline LP component's exact mathematical structure
(``components/constraints/inventory_balance.py``, ``demand.py``, ``utilization.py``,
``counterparty.py``) once per planning period, as **plain functions rather than registered
``@constraint_component`` classes** -- the existing ``ConstraintComponent`` protocol has no period
parameter and every baseline component hardcodes an unsuffixed ``VariableKey("q", route.route_id)``,
which would collide period 0's ``q`` with period 5's ``q`` under one shared variable index (see
``specs/0010-multi-period-settlement/plan.md``'s "Architecture & Components" section). Row/bound
construction here reuses each baseline component's *formula*, not its *code*.

Variables are period-suffixed (``f"{scope_id}@{period_index:03d}"``, zero-padded for the same
lexicographic-order reason ``specs/0009-discrete-fee-tier-pricing/`` zero-pads its own tier index)
and built once per request via ``build_multi_period_variable_index`` -- the plain, non-suffixed
``q``/``inc``/``dec``/``a`` blocks ``formulation.context.build_context`` builds for the
single-period compilers are not used at all here.

**Two Phase-2-only bound-tightening rules, not spelled out formula-by-formula in ``plan.md``, are
recorded here rather than guessed silently (constitution P8):**

1. ``RETURN`` (voluntary, borrower-initiated) lowers *both* ``maximum_quantity_shares`` and
   ``hard_minimum_quantity_shares`` by the returned quantity (each floored at zero) -- unlike
   ``RECALL`` (a lender's contractual pull), which lowers only ``maximum_quantity_shares``, floored
   at the *unchanged* ``hard_minimum_quantity_shares`` (the same formula
   ``scenarios.apply._apply_trade_event``'s ``RECALL`` branch already uses). ``plan.md``'s own text
   names both fields for ``RETURN`` but only one for ``RECALL``, which this reads as deliberate.
2. An already-ineligible route (``route.eligible is False`` at the request's own baseline; no
   ``known_future_event`` type ever flips a route from eligible to ineligible -- only ``NEW_LOAN``
   flips the other way) has no period-``(t-1)`` scalar to clamp its run-off ceiling against for
   ``t >= 1`` the way ``formulation.compiler_support.set_route_bounds`` clamps to a concrete
   ``current_quantity_shares`` at period 0 -- period ``t-1``'s own quantity is itself a free
   variable. V1 conservatively clamps such a route's upper bound, at every period, to its own
   period-0 baseline ``current_quantity_shares`` (never looser than today's single-period
   behavior) rather than expressing a genuine variable-relative constraint -- deferred, not
   silently dropped.

Not built here (later tasks): the discounted objective (T-009,
``components/objective_terms/multi_period_economics.py``) and ``compile_multi_period_lp``/
``solve_multi_period`` (T-010), which will call ``build_multi_period_context``/
``build_multi_period_variable_index``/``contribute_all_periods`` from this module plus T-009's
objective term to assemble one ``CompiledProblem`` and solve it.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TypeVar

from inventory_optimizer.config.models import ElasticityConfig, InventoryOptimizerConfig
from inventory_optimizer.domain.enums import TradeEventType
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.policies import CounterpartyLimit, UtilizationPolicy
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.scenarios import TradeEvent
from inventory_optimizer.elasticity import EvaluatedDemand, evaluate_demand_cap
from inventory_optimizer.exceptions import InputValidationError, ValidationIssue
from inventory_optimizer.formulation.indexes import VariableIndex, VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder
from inventory_optimizer.formulation.variables import build_variable_index
from inventory_optimizer.scenarios.apply import select_effective_events

T = TypeVar("T")

PERIOD_SEPARATOR = "@"
# RISK-004: the same "validated, not assumed" cap specs/0009-discrete-fee-tier-pricing/ applies to
# its own zero-padded tier index -- both share the three-digit zero-pad, so both share this ceiling.
MAX_PERIODS = 1000


def period_scope_id(base_id: str, period_index: int) -> str:
    """The period-``period_index`` variable/row scope id for ``base_id`` (a route or inventory
    id). Zero-padded to three digits so lexicographic sort order (Section 16.5) matches numeric
    period order, mirroring ``formulation.context.tier_scope_id``'s own convention."""
    return f"{base_id}{PERIOD_SEPARATOR}{period_index:03d}"


def period_variable_key(kind: str, base_id: str, period_index: int) -> VariableKey:
    return VariableKey(kind=kind, scope_id=period_scope_id(base_id, period_index))


def _group_by(items: Iterable[T], *, key: Callable[[T], str]) -> dict[str, tuple[T, ...]]:
    grouped: dict[str, list[T]] = defaultdict(list)
    for item in items:
        grouped[key(item)].append(item)
    return {group_key: tuple(values) for group_key, values in grouped.items()}


def _compute_demand_caps(
    request: OptimizationRequest, elasticity_config: ElasticityConfig
) -> dict[str, EvaluatedDemand]:
    """A related-but-distinct reuse of ``formulation.context._compute_demand_caps``'s formula
    (not its code, per this module's own docstring): no tiered-demand-group skip is needed here,
    since ``formulation.compiler_support.multi_period_conflict_issues`` already fails closed on any
    request combining ``planning_periods`` with a candidate-fee-tier menu. Demand caps are held
    constant across every period (spec.md Non-Goals: "time-varying demand forecasts... across the
    horizon"), so this runs once per request, not once per period."""
    routes_by_group = _group_by(request.routes, key=lambda route: route.demand_group_id)
    caps: dict[str, EvaluatedDemand] = {}
    for forecast in request.demand:
        group_routes = routes_by_group.get(forecast.demand_group_id, ())
        evaluated_fee = group_routes[0].fee_rate if group_routes else forecast.reference_fee_rate
        caps[forecast.demand_group_id] = evaluate_demand_cap(
            forecast, evaluated_fee, config=elasticity_config
        )
    return caps


def _policy_applies(policy: UtilizationPolicy, inventory: SecurityInventory) -> bool:
    if (
        policy.inventory_pool_id is not None
        and policy.inventory_pool_id != inventory.inventory_pool_id
    ):
        return False
    if policy.security_id is not None and policy.security_id != inventory.security_id:
        return False
    return True


def _limit_in_scope(
    limit: CounterpartyLimit, route: LoanRoute, inventory: SecurityInventory
) -> bool:
    if limit.security_id is not None and limit.security_id != route.security_id:
        return False
    if (
        limit.inventory_pool_id is not None
        and limit.inventory_pool_id != inventory.inventory_pool_id
    ):
        return False
    return True


@dataclass(frozen=True, slots=True)
class PeriodBoundAdjustments:
    """REQ-010: the cumulative effect of ``known_future_events`` on period-``t`` route/inventory
    bounds, keyed by ``period_index`` (``1..N`` only -- period 0 carries no adjustments, since every
    planning boundary is strictly later than ``effective_date`` and ``select_effective_events``
    therefore never returns anything for the ``(-inf, effective_date]`` window period 0 occupies).

    Distinct from ``scenarios.apply.apply_events`` (RISK-003): a route's quantity at period
    ``t >= 1`` is a free decision variable, not a settled snapshot, so an event can only
    tighten/widen the *bound* that variable must respect at every period on or after it takes
    effect -- it cannot compute a concrete forced value the way ``apply_events`` does for a fully-
    determined state. Each mapping already carries every period-``t``-and-later period's own
    cumulative value (not a delta), so a row-building function reads
    ``.get(period_index, {}).get(scope_id, <period-0 baseline>)`` directly.
    """

    lendable_delta_by_inventory: Mapping[int, Mapping[str, float]]
    max_quantity_by_route: Mapping[int, Mapping[str, float]]
    hard_minimum_by_route: Mapping[int, Mapping[str, float]]


def _apply_bound_event(
    event: TradeEvent,
    inventory_by_id: Mapping[str, SecurityInventory],
    lendable_delta: dict[str, float],
    max_quantity: dict[str, float],
    hard_minimum: dict[str, float],
) -> None:
    if event.event_type in (TradeEventType.BUY, TradeEventType.TRANSFER_IN):
        assert event.inventory_id is not None
        if event.event_type is TradeEventType.TRANSFER_IN and not (
            inventory_by_id[event.inventory_id].eligible
        ):
            return  # destination pool ineligible; transfer has no effect (Section 13.1)
        lendable_delta[event.inventory_id] += event.quantity_shares
    elif event.event_type in (TradeEventType.SELL, TradeEventType.TRANSFER_OUT):
        assert event.inventory_id is not None
        lendable_delta[event.inventory_id] -= event.quantity_shares
    elif event.event_type is TradeEventType.NEW_LOAN:
        assert event.route_id is not None
        max_quantity[event.route_id] = max(max_quantity[event.route_id], event.quantity_shares)
    elif event.event_type is TradeEventType.RETURN:
        # Decision 1 (this module's docstring): lowers both the cap and the floor, floored at zero.
        assert event.route_id is not None
        route_id = event.route_id
        new_hard_minimum = max(hard_minimum[route_id] - event.quantity_shares, 0.0)
        new_max = max(max_quantity[route_id] - event.quantity_shares, new_hard_minimum)
        hard_minimum[route_id] = new_hard_minimum
        max_quantity[route_id] = new_max
    elif event.event_type is TradeEventType.RECALL:
        # Same `new_max` formula `scenarios.apply._apply_trade_event`'s RECALL branch uses --
        # floored at the *unchanged* hard_minimum.
        assert event.route_id is not None
        route_id = event.route_id
        max_quantity[route_id] = max(
            max_quantity[route_id] - event.quantity_shares, hard_minimum[route_id]
        )


def compute_period_bound_adjustments(
    request: OptimizationRequest, boundaries: Sequence[date]
) -> PeriodBoundAdjustments:
    """REQ-010. ``boundaries`` is ``(request.effective_date, *request.planning_periods)``, the same
    shape ``settlement.project.project_multi_period`` builds. Events are consumed cumulatively,
    period by period, in ``select_effective_events``'s existing deterministic order -- the same
    ordering rule Phase 1 uses, applied here to accumulate bound values instead of mutating a
    snapshot."""
    inventory_by_id = {inventory.inventory_id: inventory for inventory in request.inventory}
    lendable_delta: dict[str, float] = defaultdict(float)
    max_quantity: dict[str, float] = {
        route.route_id: route.maximum_quantity_shares for route in request.routes
    }
    hard_minimum: dict[str, float] = {
        route.route_id: route.hard_minimum_quantity_shares for route in request.routes
    }

    lendable_by_period: dict[int, dict[str, float]] = {}
    max_by_period: dict[int, dict[str, float]] = {}
    hard_minimum_by_period: dict[int, dict[str, float]] = {}

    for period_index in range(1, len(boundaries)):
        events = select_effective_events(
            request.known_future_events,
            after=boundaries[period_index - 1],
            on_or_before=boundaries[period_index],
        )
        for event in events:
            _apply_bound_event(event, inventory_by_id, lendable_delta, max_quantity, hard_minimum)
        lendable_by_period[period_index] = dict(lendable_delta)
        max_by_period[period_index] = dict(max_quantity)
        hard_minimum_by_period[period_index] = dict(hard_minimum)

    return PeriodBoundAdjustments(
        lendable_delta_by_inventory=lendable_by_period,
        max_quantity_by_route=max_by_period,
        hard_minimum_by_route=hard_minimum_by_period,
    )


@dataclass(frozen=True, slots=True)
class MultiPeriodContext:
    """Everything a period-indexed row-building function needs -- the Phase 2 analogue of
    ``formulation.context.BuildContext``, but holding no ``VariableIndex`` of its own (a component
    only ever reaches a variable's *position* through ``SparseBuilder``, keyed by
    ``period_variable_key``; nothing here needs the index directly)."""

    request: OptimizationRequest
    config: InventoryOptimizerConfig
    boundaries: tuple[date, ...]
    inventory_by_id: Mapping[str, SecurityInventory]
    routes_by_inventory: Mapping[str, tuple[LoanRoute, ...]]
    routes_by_demand_group: Mapping[str, tuple[LoanRoute, ...]]
    routes_by_borrower: Mapping[str, tuple[LoanRoute, ...]]
    demand_caps: Mapping[str, EvaluatedDemand]
    adjustments: PeriodBoundAdjustments

    @property
    def period_count(self) -> int:
        """Number of periods, ``0..N`` inclusive (``N = len(request.planning_periods)``)."""
        return len(self.boundaries)


def build_multi_period_context(
    request: OptimizationRequest, config: InventoryOptimizerConfig
) -> MultiPeriodContext:
    boundaries = (request.effective_date, *request.planning_periods)
    return MultiPeriodContext(
        request=request,
        config=config,
        boundaries=boundaries,
        inventory_by_id={inventory.inventory_id: inventory for inventory in request.inventory},
        routes_by_inventory=_group_by(request.routes, key=lambda route: route.inventory_id),
        routes_by_demand_group=_group_by(request.routes, key=lambda route: route.demand_group_id),
        routes_by_borrower=_group_by(request.routes, key=lambda route: route.borrower_id),
        demand_caps=_compute_demand_caps(request, config.elasticity),
        adjustments=compute_period_bound_adjustments(request, boundaries),
    )


def build_multi_period_variable_index(request: OptimizationRequest) -> VariableIndex:
    """REQ-009's "Variables" section: one period-suffixed ``q``/``inc``/``dec``/``a`` block per
    ``kind``, spanning periods ``0..N``. Raises ``InputValidationError`` above ``MAX_PERIODS`` --
    validated, not assumed, mirroring ``specs/0009-discrete-fee-tier-pricing/``'s own tier-index
    cap. This is Phase 2's own scaling limit on the joint LP specifically (Design B's projection has
    no variable-count concern at all), so it lives here rather than as a ``domain.requests.
    OptimizationRequest`` field validator."""
    period_count = len(request.planning_periods) + 1
    if period_count > MAX_PERIODS:
        raise InputValidationError(
            (
                ValidationIssue(
                    code="MULTI_PERIOD_TOO_MANY_PERIODS",
                    message=(
                        f"planning_periods implies {period_count} periods (0..N inclusive), "
                        f"exceeding the {MAX_PERIODS} the zero-padded period variable-key index "
                        "spans"
                    ),
                    location="request.planning_periods",
                ),
            )
        )

    route_ids = [route.route_id for route in request.routes]
    inventory_ids = [inventory.inventory_id for inventory in request.inventory]
    blocks: list[tuple[str, list[str]]] = []
    for kind, scope_ids in (("q", route_ids), ("inc", route_ids), ("dec", route_ids)):
        blocks.append(
            (
                kind,
                [
                    period_scope_id(scope_id, t)
                    for t in range(period_count)
                    for scope_id in scope_ids
                ],
            )
        )
    blocks.append(
        (
            "a",
            [
                period_scope_id(scope_id, t)
                for t in range(period_count)
                for scope_id in inventory_ids
            ],
        )
    )
    return build_variable_index(blocks)


def _period_lendable(
    inventory: SecurityInventory, adjustments: PeriodBoundAdjustments, period_index: int
) -> float:
    delta = adjustments.lendable_delta_by_inventory.get(period_index, {}).get(
        inventory.inventory_id, 0.0
    )
    return inventory.total_lendable_shares + delta


def set_route_bounds_for_period(
    context: MultiPeriodContext, builder: SparseBuilder, period_index: int
) -> None:
    """Section 11.5/11.3, period-parameterized. Period 0 is byte-identical to
    ``formulation.compiler_support.set_route_bounds`` (REQ-009); period ``t >= 1`` uses this
    module's own two recorded decisions for the ineligible-route clamp and the event-adjusted
    bounds (this module's own docstring)."""
    for route in context.request.routes:
        if period_index == 0:
            lower = route.hard_minimum_quantity_shares
            upper = (
                route.maximum_quantity_shares
                if route.eligible
                else min(route.maximum_quantity_shares, route.current_quantity_shares)
            )
            upper = max(upper, lower)
        else:
            lower = context.adjustments.hard_minimum_by_route.get(period_index, {}).get(
                route.route_id, route.hard_minimum_quantity_shares
            )
            upper = context.adjustments.max_quantity_by_route.get(period_index, {}).get(
                route.route_id, route.maximum_quantity_shares
            )
            if not route.eligible:
                upper = min(upper, route.current_quantity_shares)
            upper = max(upper, lower)
        builder.set_variable_bounds(
            period_variable_key("q", route.route_id, period_index), lower=lower, upper=upper
        )

        if period_index == 0:
            # REQ-009: period 0's inc/dec bounds are exactly today's baseline formula.
            inc_upper = max(upper - route.current_quantity_shares, 0.0)
            dec_upper = max(route.current_quantity_shares - lower, 0.0)
            builder.set_variable_bounds(
                period_variable_key("inc", route.route_id, 0), lower=0.0, upper=inc_upper
            )
            builder.set_variable_bounds(
                period_variable_key("dec", route.route_id, 0), lower=0.0, upper=dec_upper
            )
        # else: inc_{j,t}/dec_{j,t} keep SparseBuilder's default [0, inf) bounds. Their tight upper
        # bound would depend on q_{j,t-1}, itself a free variable at t-1 >= 0 once t >= 2 -- no
        # static bound is computable. The transition identity plus a maximizing objective
        # penalizing both (Section 11.3's own degeneracy note) already pins them at zero unless
        # genuinely forced, so correctness does not depend on a tighter bound here.


def contribute_inventory_balance(
    context: MultiPeriodContext, builder: SparseBuilder, period_index: int
) -> None:
    """Section 11.4, period-parameterized: ``sum(q_{j,t}) + a_{i,t} = L_i,t - R_i,t - C_i,t``.
    ``R_i``/``C_i`` (``reserved_shares``/``committed_out_shares``) are held constant across every
    period -- no ``known_future_event`` type touches either field (spec.md Non-Goals)."""
    for inventory in context.request.inventory:
        lendable = _period_lendable(inventory, context.adjustments, period_index)
        rhs = lendable - inventory.reserved_shares - inventory.committed_out_shares
        row = builder.add_row(
            "inventory_balance", period_scope_id(inventory.inventory_id, period_index),
            lower=rhs, upper=rhs,
        )
        for route in context.routes_by_inventory.get(inventory.inventory_id, ()):
            builder.add_row_coefficient(
                row, period_variable_key("q", route.route_id, period_index), 1.0
            )
        builder.add_row_coefficient(
            row, period_variable_key("a", inventory.inventory_id, period_index), 1.0
        )


def contribute_transition_identity(
    context: MultiPeriodContext, builder: SparseBuilder, period_index: int
) -> None:
    """Section 11.3, period-parameterized. Period 0 (``q_{j,-1} := route.current_quantity_shares``,
    a constant) is *exactly* today's existing row, unchanged -- REQ-009. Period ``t >= 1`` cannot
    use the same row shape: ``q_{j,t-1}`` is itself a decision variable, not a constant, so the row
    becomes ``q_{j,t} - q_{j,t-1} - inc_{j,t} + dec_{j,t} = 0`` (two ``q`` coefficients, RHS zero)
    rather than one ``q`` coefficient against a constant RHS."""
    for route in context.request.routes:
        scope_id = period_scope_id(route.route_id, period_index)
        if period_index == 0:
            row = builder.add_row(
                "transition_identity", scope_id,
                lower=route.current_quantity_shares, upper=route.current_quantity_shares,
            )
            builder.add_row_coefficient(row, period_variable_key("q", route.route_id, 0), 1.0)
            builder.add_row_coefficient(row, period_variable_key("inc", route.route_id, 0), -1.0)
            builder.add_row_coefficient(row, period_variable_key("dec", route.route_id, 0), 1.0)
        else:
            row = builder.add_row("transition_identity", scope_id, lower=0.0, upper=0.0)
            builder.add_row_coefficient(
                row, period_variable_key("q", route.route_id, period_index), 1.0
            )
            builder.add_row_coefficient(
                row, period_variable_key("q", route.route_id, period_index - 1), -1.0
            )
            builder.add_row_coefficient(
                row, period_variable_key("inc", route.route_id, period_index), -1.0
            )
            builder.add_row_coefficient(
                row, period_variable_key("dec", route.route_id, period_index), 1.0
            )


def contribute_demand_cap(
    context: MultiPeriodContext, builder: SparseBuilder, period_index: int
) -> None:
    """Section 11.6, period-parameterized. ``D_g`` is constant across every period (spec.md
    Non-Goals); no tiered-demand-group skip is needed (this module's own docstring)."""
    for forecast in context.request.demand:
        routes = context.routes_by_demand_group.get(forecast.demand_group_id, ())
        if not routes:
            continue
        cap = context.demand_caps[forecast.demand_group_id].effective_cap_shares
        row = builder.add_row(
            "demand_cap", period_scope_id(forecast.demand_group_id, period_index),
            lower=-math.inf, upper=cap,
        )
        for route in routes:
            builder.add_row_coefficient(
                row, period_variable_key("q", route.route_id, period_index), 1.0
            )


def contribute_utilization_cap(
    context: MultiPeriodContext, builder: SparseBuilder, period_index: int
) -> None:
    """Section 11.7, period-parameterized: ``u_min_i * L_i,t <= O_i,t <= u_max_i * L_i,t``."""
    for inventory in context.request.inventory:
        routes = context.routes_by_inventory.get(inventory.inventory_id, ())
        lendable = _period_lendable(inventory, context.adjustments, period_index)
        for policy in context.request.utilization_policies:
            if not _policy_applies(policy, inventory):
                continue
            scope_id = period_scope_id(f"{inventory.inventory_id}:{policy.policy_id}", period_index)
            if policy.maximum_utilization is not None:
                row = builder.add_row(
                    "utilization_max", scope_id,
                    lower=-math.inf, upper=policy.maximum_utilization * lendable,
                )
                for route in routes:
                    builder.add_row_coefficient(
                        row, period_variable_key("q", route.route_id, period_index), 1.0
                    )
            if policy.minimum_utilization is not None:
                row = builder.add_row(
                    "utilization_min", scope_id,
                    lower=policy.minimum_utilization * lendable, upper=math.inf,
                )
                for route in routes:
                    builder.add_row_coefficient(
                        row, period_variable_key("q", route.route_id, period_index), 1.0
                    )


def contribute_reserve_buffer_bounds(
    context: MultiPeriodContext, builder: SparseBuilder, period_index: int
) -> None:
    """Section 11.9, period-parameterized: a lower-bound tightening on ``a_{i,t}``, exactly like
    the baseline's own ``ReserveBufferConstraint`` (a variable bound, not a row)."""
    for inventory in context.request.inventory:
        lendable = _period_lendable(inventory, context.adjustments, period_index)
        buffer = 0.0
        for policy in context.request.utilization_policies:
            if not _policy_applies(policy, inventory):
                continue
            buffer = max(
                buffer, policy.reserve_buffer_shares, policy.reserve_buffer_fraction * lendable
            )
        if buffer > 0.0:
            builder.set_variable_bounds(
                period_variable_key("a", inventory.inventory_id, period_index),
                lower=buffer, upper=math.inf,
            )


def contribute_counterparty_limit(
    context: MultiPeriodContext, builder: SparseBuilder, period_index: int
) -> None:
    """Section 11.8, period-parameterized. ``K_b`` and each route's price are held constant across
    every period (spec.md Non-Goals)."""
    for limit in context.request.counterparty_limits:
        routes = [
            route
            for route in context.routes_by_borrower.get(limit.borrower_id, ())
            if _limit_in_scope(limit, route, context.inventory_by_id[route.inventory_id])
        ]
        if not routes:
            continue
        scope_id = period_scope_id(limit.limit_id, period_index)

        if limit.maximum_quantity_shares is not None:
            row = builder.add_row(
                "counterparty_quantity", scope_id,
                lower=-math.inf, upper=limit.maximum_quantity_shares,
            )
            for route in routes:
                builder.add_row_coefficient(
                    row, period_variable_key("q", route.route_id, period_index), 1.0
                )

        if limit.maximum_notional_usd is not None:
            row = builder.add_row(
                "counterparty_notional", scope_id, lower=-math.inf, upper=limit.maximum_notional_usd
            )
            for route in routes:
                price = context.inventory_by_id[route.inventory_id].price_usd
                builder.add_row_coefficient(
                    row, period_variable_key("q", route.route_id, period_index), price
                )


def contribute_period_constraints(
    context: MultiPeriodContext, builder: SparseBuilder, period_index: int
) -> None:
    """Every REQUIRED_CONSTRAINTS-equivalent row/bound for one period, in the same order
    ``formulation.lp.compile_lp`` applies them for the single-period case (bounds before rows)."""
    set_route_bounds_for_period(context, builder, period_index)
    contribute_inventory_balance(context, builder, period_index)
    contribute_transition_identity(context, builder, period_index)
    contribute_demand_cap(context, builder, period_index)
    contribute_utilization_cap(context, builder, period_index)
    contribute_reserve_buffer_bounds(context, builder, period_index)
    contribute_counterparty_limit(context, builder, period_index)


def contribute_all_periods(context: MultiPeriodContext, builder: SparseBuilder) -> None:
    """Every period's constraints, period 0 through N, in period order."""
    for period_index in range(context.period_count):
        contribute_period_constraints(context, builder, period_index)
