"""Scenario comparison assembly (T13-T14; Section 13.4).

Reads two already-built ``OptimizationResult``s (baseline, scenario) plus the two requests that
produced them -- never a ``VerifiedSolution``, matching T11's ``ExplanationServiceImpl`` precedent
of reading only already-assembled results, not re-deriving from solver internals.
"""

from __future__ import annotations

from inventory_optimizer.components.objective_terms.fee_revenue import fee_revenue_coefficient
from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.domain.enums import ReasonCode, TradeEventType
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.results import OptimizationResult
from inventory_optimizer.domain.scenario_results import (
    InventoryBalanceDelta,
    RouteAllocationDelta,
    ScenarioComparison,
)
from inventory_optimizer.domain.scenarios import Scenario
from inventory_optimizer.validation import DEFAULT_TOLERANCE

_SUPPLY_REDUCING_TYPES = frozenset({TradeEventType.SELL, TradeEventType.TRANSFER_OUT})
_ROUTE_REDUCING_TYPES = frozenset({TradeEventType.RETURN, TradeEventType.RECALL})


def _trade_affected_route_ids(
    scenario: Scenario, baseline_request: OptimizationRequest
) -> frozenset[str]:
    """Routes whose allocation drop is attributable to this scenario's trade events: those
    sharing an inventory record an effective SELL/TRANSFER_OUT touched, plus any route an
    effective RETURN/RECALL directly targeted."""
    effective = [
        event
        for event in scenario.trade_events
        if event.effective_date <= baseline_request.effective_date
    ]
    reduced_inventory_ids = {
        event.inventory_id for event in effective if event.event_type in _SUPPLY_REDUCING_TYPES
    }
    directly_targeted_route_ids = {
        event.route_id for event in effective if event.event_type in _ROUTE_REDUCING_TYPES
    }
    routes_sharing_reduced_inventory = {
        route.route_id
        for route in baseline_request.routes
        if route.inventory_id in reduced_inventory_ids
    }
    return frozenset(routes_sharing_reduced_inventory | directly_targeted_route_ids)


def build_scenario_comparison(
    *,
    scenario: Scenario,
    baseline_request: OptimizationRequest,
    baseline_result: OptimizationResult,
    scenario_request: OptimizationRequest,
    scenario_result: OptimizationResult,
    config: InventoryOptimizerConfig,
    apply_warnings: tuple[str, ...] = (),
) -> ScenarioComparison:
    affected_route_ids = _trade_affected_route_ids(scenario, baseline_request)
    scenario_route_by_id = {route.route_id: route for route in scenario_request.routes}
    scenario_inventory_by_id = {inv.inventory_id: inv for inv in scenario_request.inventory}

    baseline_allocation_by_route = {a.route_id: a for a in baseline_result.allocations}
    scenario_allocation_by_route = {a.route_id: a for a in scenario_result.allocations}

    allocation_deltas: list[RouteAllocationDelta] = []
    for route_id, baseline_alloc in baseline_allocation_by_route.items():
        scenario_alloc = scenario_allocation_by_route.get(route_id)
        if scenario_alloc is None:
            continue
        delta = scenario_alloc.post_quantity_shares - baseline_alloc.post_quantity_shares
        reason_codes: list[ReasonCode] = []
        estimated_revenue_delta: float | None = None
        if delta < -DEFAULT_TOLERANCE and route_id in affected_route_ids:
            reason_codes.append(ReasonCode.TRADE_REDUCED_SUPPLY)
            route = scenario_route_by_id[route_id]
            inventory = scenario_inventory_by_id[route.inventory_id]
            coefficient = fee_revenue_coefficient(route, inventory, config.formulation)
            estimated_revenue_delta = delta * coefficient
        allocation_deltas.append(
            RouteAllocationDelta(
                route_id=route_id,
                baseline_quantity_shares=baseline_alloc.post_quantity_shares,
                scenario_quantity_shares=scenario_alloc.post_quantity_shares,
                delta_shares=delta,
                reason_codes=tuple(reason_codes),
                estimated_revenue_delta_usd=estimated_revenue_delta,
            )
        )

    baseline_balance_by_id = {b.inventory_id: b for b in baseline_result.balances}
    scenario_balance_by_id = {b.inventory_id: b for b in scenario_result.balances}
    balance_deltas = [
        InventoryBalanceDelta(
            inventory_id=inventory_id,
            baseline_total_lendable_shares=baseline_balance.pre_total_lendable_shares,
            scenario_total_lendable_shares=scenario_balance_by_id[inventory_id].pre_total_lendable_shares,
            baseline_available_shares=baseline_balance.post_available_shares,
            scenario_available_shares=scenario_balance_by_id[inventory_id].post_available_shares,
            baseline_utilization=baseline_balance.utilization,
            scenario_utilization=scenario_balance_by_id[inventory_id].utilization,
        )
        for inventory_id, baseline_balance in baseline_balance_by_id.items()
        if inventory_id in scenario_balance_by_id
    ]

    baseline_components = {
        c.component_name: c.unscaled_value_usd for c in baseline_result.economics.components
    }
    scenario_components = {
        c.component_name: c.unscaled_value_usd for c in scenario_result.economics.components
    }
    component_deltas = {
        name: scenario_components.get(name, 0.0) - baseline_components.get(name, 0.0)
        for name in set(baseline_components) | set(scenario_components)
    }

    baseline_unfilled = sum(d.unfilled_shares for d in baseline_result.demand)
    scenario_unfilled = sum(d.unfilled_shares for d in scenario_result.demand)

    return ScenarioComparison(
        scenario_id=scenario.scenario_id,
        scenario_name=scenario.name,
        baseline_run_id=baseline_result.run_id,
        scenario_run_id=scenario_result.run_id,
        status=scenario_result.status,
        verification_passed=scenario_result.verification.passed,
        objective_delta_usd=(
            scenario_result.economics.total_value_usd - baseline_result.economics.total_value_usd
        ),
        economics_component_deltas=component_deltas,
        balances=tuple(balance_deltas),
        allocations=tuple(allocation_deltas),
        unfilled_demand_delta_shares=scenario_unfilled - baseline_unfilled,
        warnings=tuple(apply_warnings) + scenario_result.warnings,
        config_hash=scenario_result.config_hash,
        baseline_input_hash=baseline_result.input_hash,
        scenario_input_hash=scenario_result.input_hash,
    )
