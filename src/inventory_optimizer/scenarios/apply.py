"""Scenario overlay application (T13-T14; Section 13.2-13.3; SCN-001, SCN-002).

``apply_scenario`` is a pure function: it reads the baseline request and a ``Scenario`` and
returns a brand-new ``OptimizationRequest``, never mutating its input (every domain contract here
is already frozen; this module additionally never calls ``.model_validate()``/``model_dump_json()``
on the result -- see the module-level note below and
``specs/0004-scenario-engine/plan.md``'s "Reconciling a sale against an existing book").

Trade events are applied only if ``effective_date <= baseline.effective_date`` (Section 13.2), in a
deterministic order (Section 13.3 step 3): ``(effective_date, type-priority, event_id)``, where
type priority is ``TradeEventType``'s own declaration order (documented there; no other ordering is
given anywhere in ``01_SPEC.md``). Rate/demand shocks are applied unconditionally -- they represent
scenario-level market assumptions, not dated real-world events.

**Why this never re-validates through ``model_validate``:** a scenario-modified
``SecurityInventory`` can legitimately become "oversold" (``on_loan_shares >
total_lendable_shares``, ``available_to_lend_shares < 0``) when a sale is booked before its
offsetting recall completes -- exactly ``EXAMPLES.md``'s E3. ``SecurityInventory``'s own field
constraints correctly reject this at *construction* time for the steady-state ingestion path;
re-running that same check against a
scenario's deliberately-stressed state would make E3 impossible to represent. ``.model_copy()``
never re-runs those checks, and the LP itself never reads ``on_loan_shares``/
``available_to_lend_shares`` (only ``total_lendable_shares``/``reserved_shares``/
``committed_out_shares``, and ``route.current_quantity_shares`` as the transition baseline) -- so
the solve is unaffected. Callers must keep the result in-process (never serialize it to JSON and
reload it) through to ``InventoryOptimizer.optimize()``.

``select_effective_events``/``apply_events`` (specs/0010-multi-period-settlement/) are
``apply_scenario``'s own filter/apply logic, promoted from private to package-shared -- the same
move ``formulation.compiler_support`` already made for ``resolve_component``/``set_route_bounds``
when a second compiler needed them. ``select_effective_events`` generalizes the single
``effective_date <= baseline.effective_date`` cutoff to an arbitrary ``(after, on_or_before]``
window, and ``apply_events`` is the per-event-type mutation loop, now reusable per period by
``settlement.project.project_multi_period`` -- called once per period instead of once per whole
scenario, with no change to what any individual event *means*. ``apply_scenario`` itself is now a
thin wrapper around both; its own behavior for a single cutoff date is unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from inventory_optimizer.domain.demand import DemandForecast
from inventory_optimizer.domain.enums import TradeEventType
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.scenarios import DemandShock, RateShock, Scenario, TradeEvent
from inventory_optimizer.exceptions import ScenarioApplicationError

_TYPE_PRIORITY: dict[TradeEventType, int] = {
    event_type: position for position, event_type in enumerate(TradeEventType)
}
_SUPPLY_DECREASE_TYPES = frozenset({TradeEventType.SELL, TradeEventType.TRANSFER_OUT})
_SUPPLY_INCREASE_TYPES = frozenset({TradeEventType.BUY, TradeEventType.TRANSFER_IN})


def select_effective_events(
    events: Sequence[TradeEvent], *, after: date | None, on_or_before: date
) -> list[TradeEvent]:
    """Section 13.3 step 3's deterministic order -- ``(effective_date, type-priority,
    event_id)`` -- generalized to an arbitrary ``(after, on_or_before]`` window instead of always
    ``(-inf, baseline.effective_date]``. ``after=None`` means unbounded below, matching
    ``apply_scenario``'s own original ``<=`` filter exactly."""
    return sorted(
        (
            event
            for event in events
            if (after is None or event.effective_date > after)
            and event.effective_date <= on_or_before
        ),
        key=lambda event: (event.effective_date, _TYPE_PRIORITY[event.event_type], event.event_id),
    )


def apply_events(
    baseline: OptimizationRequest, events: Sequence[TradeEvent]
) -> tuple[OptimizationRequest, tuple[str, ...]]:
    """Apply an already-selected, already-ordered sequence of trade events (see
    ``select_effective_events``) to ``baseline``, returning a new request and any warnings.
    Never mutates ``baseline``. Callers own event selection/ordering and any conflict checks --
    this function only applies what it is given, in the order it is given."""
    inventory_by_id = {inventory.inventory_id: inventory for inventory in baseline.inventory}
    routes_by_id = {route.route_id: route for route in baseline.routes}
    warnings: list[str] = []

    for event in events:
        _apply_trade_event(event, inventory_by_id, routes_by_id, warnings)

    updated = baseline.model_copy(
        update={
            "inventory": tuple(inventory_by_id[i.inventory_id] for i in baseline.inventory),
            "routes": tuple(routes_by_id[r.route_id] for r in baseline.routes),
        }
    )
    return updated, tuple(warnings)


def _check_no_conflicting_return_recall(events: Sequence[TradeEvent]) -> None:
    for conflicting_type in (TradeEventType.RETURN, TradeEventType.RECALL):
        route_ids = [event.route_id for event in events if event.event_type is conflicting_type]
        seen: set[str | None] = set()
        for route_id in route_ids:
            if route_id in seen:
                raise ScenarioApplicationError(
                    f"more than one effective {conflicting_type.value} event references "
                    f"route_id {route_id!r} -- unordered composition conflict (Section 13.2)"
                )
            seen.add(route_id)


def _adjust_total_lendable(inventory: SecurityInventory, delta: float) -> SecurityInventory:
    new_total = inventory.total_lendable_shares + delta
    if new_total < 0.0:
        raise ScenarioApplicationError(
            f"trade event would drive inventory {inventory.inventory_id!r}'s "
            f"total_lendable_shares negative ({new_total!r}); cannot sell/transfer out more than "
            "is held"
        )
    new_available = inventory.available_to_lend_shares + delta
    return inventory.model_copy(
        update={"total_lendable_shares": new_total, "available_to_lend_shares": new_available}
    )


def _adjust_on_loan(inventory: SecurityInventory, delta: float) -> SecurityInventory:
    """Used only by RETURN/RECALL, which change a specific route's booked quantity: the owning
    inventory's on_loan_shares (and, from the balance identity, available_to_lend_shares) must move
    by the same amount, or check_on_loan_reconciliation (re-run per REQ-006) would immediately
    fail."""
    return inventory.model_copy(
        update={
            "on_loan_shares": inventory.on_loan_shares + delta,
            "available_to_lend_shares": inventory.available_to_lend_shares - delta,
        }
    )


def _apply_trade_event(
    event: TradeEvent,
    inventory_by_id: dict[str, SecurityInventory],
    routes_by_id: dict[str, LoanRoute],
    warnings: list[str],
) -> None:
    if event.event_type in _SUPPLY_INCREASE_TYPES:
        assert event.inventory_id is not None
        inventory = inventory_by_id[event.inventory_id]
        if event.event_type is TradeEventType.TRANSFER_IN and not inventory.eligible:
            return  # destination pool ineligible; transfer has no effect (Section 13.1)
        inventory_by_id[event.inventory_id] = _adjust_total_lendable(
            inventory, event.quantity_shares
        )
    elif event.event_type in _SUPPLY_DECREASE_TYPES:
        assert event.inventory_id is not None
        inventory = inventory_by_id[event.inventory_id]
        updated = _adjust_total_lendable(inventory, -event.quantity_shares)
        if updated.available_to_lend_shares < 0.0:
            warnings.append(
                f"inventory {event.inventory_id!r} is oversold pending recall after event "
                f"{event.event_id!r}: available_to_lend_shares would be "
                f"{updated.available_to_lend_shares!r}"
            )
        inventory_by_id[event.inventory_id] = updated
    elif event.event_type is TradeEventType.NEW_LOAN:
        assert event.route_id is not None
        route = routes_by_id[event.route_id]
        new_max = max(route.maximum_quantity_shares, event.quantity_shares)
        routes_by_id[event.route_id] = route.model_copy(
            update={"eligible": True, "maximum_quantity_shares": new_max}
        )
    elif event.event_type is TradeEventType.RETURN:
        assert event.route_id is not None
        route = routes_by_id[event.route_id]
        returned = min(event.quantity_shares, route.current_quantity_shares)
        routes_by_id[event.route_id] = route.model_copy(
            update={"current_quantity_shares": route.current_quantity_shares - returned}
        )
        if returned > 0.0:
            inventory_by_id[route.inventory_id] = _adjust_on_loan(
                inventory_by_id[route.inventory_id], -returned
            )
    elif event.event_type is TradeEventType.RECALL:
        assert event.route_id is not None
        route = routes_by_id[event.route_id]
        new_max = max(
            route.maximum_quantity_shares - event.quantity_shares,
            route.hard_minimum_quantity_shares,
        )
        forced_reduction = max(route.current_quantity_shares - new_max, 0.0)
        routes_by_id[event.route_id] = route.model_copy(
            update={
                "maximum_quantity_shares": new_max,
                "current_quantity_shares": route.current_quantity_shares - forced_reduction,
            }
        )
        if forced_reduction > 0.0:
            inventory_by_id[route.inventory_id] = _adjust_on_loan(
                inventory_by_id[route.inventory_id], -forced_reduction
            )


def _apply_rate_shock(shock: RateShock, routes_by_id: dict[str, LoanRoute]) -> None:
    route = routes_by_id[shock.route_id]
    routes_by_id[shock.route_id] = route.model_copy(update={"fee_rate": shock.new_fee_rate})


def _apply_demand_shock(shock: DemandShock, demand_by_group: dict[str, DemandForecast]) -> None:
    forecast = demand_by_group[shock.demand_group_id]
    update = {
        field: value
        for field, value in (
            ("reference_quantity_shares", shock.reference_quantity_shares),
            ("reference_fee_rate", shock.reference_fee_rate),
            ("elasticity", shock.elasticity),
            ("hard_max_quantity_shares", shock.hard_max_quantity_shares),
        )
        if value is not None
    }
    demand_by_group[shock.demand_group_id] = forecast.model_copy(update=update)


def apply_scenario(
    baseline: OptimizationRequest, scenario: Scenario
) -> tuple[OptimizationRequest, tuple[str, ...]]:
    """Returns the scenario-modified request and any warnings surfaced while applying it (e.g. an
    oversold-pending-recall inventory) -- never mutates ``baseline``."""
    _check_no_conflicting_return_recall(scenario.trade_events)

    effective_events = select_effective_events(
        scenario.trade_events, after=None, on_or_before=baseline.effective_date
    )
    updated, warnings = apply_events(baseline, effective_events)

    routes_by_id = {route.route_id: route for route in updated.routes}
    demand_by_group = {forecast.demand_group_id: forecast for forecast in updated.demand}
    for shock in scenario.rate_shocks:
        _apply_rate_shock(shock, routes_by_id)
    for shock in scenario.demand_shocks:
        _apply_demand_shock(shock, demand_by_group)

    scenario_request = updated.model_copy(
        update={
            "request_id": f"{baseline.request_id}::{scenario.scenario_id}",
            "routes": tuple(routes_by_id[r.route_id] for r in updated.routes),
            "demand": tuple(demand_by_group[d.demand_group_id] for d in updated.demand),
        }
    )
    return scenario_request, warnings
