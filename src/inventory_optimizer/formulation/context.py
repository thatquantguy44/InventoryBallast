"""``BuildContext`` (Section 15.2): everything a constraint/objective component needs to
``contribute()`` to one compiled LP.

Kept separate from ``formulation/lp.py`` (the compiler) so concrete components can depend on this
module without creating an import cycle: components need ``BuildContext``'s *shape*, while
``lp.py`` needs to import the components themselves to trigger their registration.

``build_context()`` (T12) is the single place that assembles a ``BuildContext`` from a request and
config -- ``formulation.lp.compile_lp`` calls it internally (this is a same-behavior extraction of
what used to be inline there), and ``facade.InventoryOptimizer`` calls it independently to obtain
the ``BuildContext`` a ``reporting.types.VerifiedSolution`` needs, without either widening
``compile_lp``'s return signature or reaching into another module's private helpers.

``activation_route_ids``/``lot_size_route_ids`` (T15; Section 14.1) are computed here, once, for
the same reason ``demand_caps``/``routes_by_*`` already are: multiple MIP-only constraint
components (``components.constraints.mip_rules``) need the same route sets, and
``compile_lp``/``compile_mip`` share one variable-index shape either way. The ``z``/``n`` variable
blocks these sets produce are empty whenever no route/policy needs them -- ``build_variable_index``
contributes zero keys for an empty scope-id list, so a request with no MIP trigger gets exactly the
same ``q``/``inc``/``dec``/``a`` positions it always has (NFR-001 in
``specs/0006-mip-business-rules/``).

``tiered_demand_group_ids``/``tier_caps`` (specs/0009-discrete-fee-tier-pricing/) follow the exact
same pattern for Section 12.4's discrete fee-tier pricing: ``tier_caps`` precomputes one
``EvaluatedDemand`` per candidate fee via the unchanged ``elasticity.evaluate_demand_cap`` (the
same call ``_compute_demand_caps`` already makes once per group, just repeated once per candidate
fee), and the ``"t"``/``"w"`` variable blocks it drives are empty for every untiered request.
``tier_scope_id``/``route_tier_scope_id`` are this spec's one, shared encoding of the composite
``(group, tier)``/``(route, tier)`` variable-key scope ids -- used by
``components.constraints.fee_tiers``, ``components.objective_terms.tier_pricing``, and
``reporting.result_builder`` alike, so there is exactly one place that owns the reserved-separator
convention (REQ-008).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from inventory_optimizer.config.models import ElasticityConfig, InventoryOptimizerConfig
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.policies import UtilizationPolicy
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.elasticity import EvaluatedDemand, evaluate_demand_cap
from inventory_optimizer.formulation.indexes import VariableIndex
from inventory_optimizer.formulation.variables import build_variable_index

T = TypeVar("T")

TIER_SEPARATOR = "#"


def tier_scope_id(demand_group_id: str, tier_index: int) -> str:
    """The ``"t"`` variable-key scope id for candidate tier ``tier_index`` of ``demand_group_id``
    (also reused for the matching ``tier_capacity`` row). Zero-padded to three digits so
    lexicographic sort order (Section 16.5) matches numeric tier order."""
    return f"{demand_group_id}{TIER_SEPARATOR}{tier_index:03d}"


def route_tier_scope_id(route_id: str, tier_index: int) -> str:
    """The ``"w"`` variable-key scope id for ``route_id``'s quantity at candidate tier
    ``tier_index``."""
    return f"{route_id}{TIER_SEPARATOR}{tier_index:03d}"


@dataclass(frozen=True, slots=True)
class BuildContext:
    request: OptimizationRequest
    config: InventoryOptimizerConfig
    variable_index: VariableIndex
    demand_caps: Mapping[str, EvaluatedDemand]
    inventory_by_id: Mapping[str, SecurityInventory]
    routes_by_inventory: Mapping[str, tuple[LoanRoute, ...]]
    routes_by_demand_group: Mapping[str, tuple[LoanRoute, ...]]
    routes_by_borrower: Mapping[str, tuple[LoanRoute, ...]]
    activation_route_ids: frozenset[str]
    lot_size_route_ids: frozenset[str]
    tiered_demand_group_ids: frozenset[str]
    tier_caps: Mapping[str, tuple[EvaluatedDemand, ...]]


def _group_by(items: Iterable[T], *, key: Callable[[T], str]) -> dict[str, tuple[T, ...]]:
    grouped: dict[str, list[T]] = defaultdict(list)
    for item in items:
        grouped[key(item)].append(item)
    return {group_key: tuple(values) for group_key, values in grouped.items()}


def _compute_demand_caps(
    request: OptimizationRequest, elasticity_config: ElasticityConfig
) -> dict[str, EvaluatedDemand]:
    """Section 12.1: elasticity runs once, before model construction. The evaluated fee for a
    group is its routes' shared ``fee_rate`` (uniform by Section 12.2, already enforced by
    ``validation.reconciliation.check_demand_group_fee_consistency``); a group with no routes yet
    falls back to its own reference fee."""
    routes_by_group = _group_by(request.routes, key=lambda route: route.demand_group_id)
    caps: dict[str, EvaluatedDemand] = {}
    for forecast in request.demand:
        group_routes = routes_by_group.get(forecast.demand_group_id, ())
        evaluated_fee = group_routes[0].fee_rate if group_routes else forecast.reference_fee_rate
        caps[forecast.demand_group_id] = evaluate_demand_cap(
            forecast, evaluated_fee, config=elasticity_config
        )
    return caps


def _compute_tier_caps(
    request: OptimizationRequest, elasticity_config: ElasticityConfig
) -> dict[str, tuple[EvaluatedDemand, ...]]:
    """Section 12.4 (REQ-002): one ``EvaluatedDemand`` per candidate fee, in the same (validated
    strictly-increasing) order as ``DemandForecast.candidate_fee_rates``, for every demand group
    that carries tiers. Elasticity remains preprocessing (Section 12.1) -- ``evaluate_demand_cap``
    itself is not modified, only called once per candidate fee instead of once per group."""
    caps: dict[str, tuple[EvaluatedDemand, ...]] = {}
    for forecast in request.demand:
        if not forecast.candidate_fee_rates:
            continue
        caps[forecast.demand_group_id] = tuple(
            evaluate_demand_cap(forecast, fee, config=elasticity_config)
            for fee in forecast.candidate_fee_rates
        )
    return caps


def _policy_applies_to_inventory(policy: UtilizationPolicy, inventory: SecurityInventory) -> bool:
    if (
        policy.inventory_pool_id is not None
        and policy.inventory_pool_id != inventory.inventory_pool_id
    ):
        return False
    if policy.security_id is not None and policy.security_id != inventory.security_id:
        return False
    return True


def _compute_activation_route_ids(
    request: OptimizationRequest, routes_by_inventory: Mapping[str, tuple[LoanRoute, ...]]
) -> frozenset[str]:
    """Section 14.1: routes needing a ``z`` binary -- ``all_or_none``,
    ``minimum_active_quantity_shares`` set, or in a cardinality (``maximum_active_routes``)
    policy's scope."""
    route_ids: set[str] = set()
    for route in request.routes:
        if route.all_or_none or route.minimum_active_quantity_shares is not None:
            route_ids.add(route.route_id)
    for policy in request.utilization_policies:
        if policy.maximum_active_routes is None:
            continue
        for inventory in request.inventory:
            if not _policy_applies_to_inventory(policy, inventory):
                continue
            for route in routes_by_inventory.get(inventory.inventory_id, ()):
                route_ids.add(route.route_id)
    return frozenset(route_ids)


def build_context(request: OptimizationRequest, config: InventoryOptimizerConfig) -> BuildContext:
    """Assemble a ``BuildContext`` from a request and config -- the same shape
    ``formulation.lp.compile_lp``/``formulation.mip.compile_mip`` build internally, exposed so any
    caller needing one (T12's facade, in order to build a ``reporting.types.VerifiedSolution``)
    does not have to duplicate or reach into another module's private helpers."""
    routes_by_inventory = _group_by(request.routes, key=lambda route: route.inventory_id)
    activation_route_ids = _compute_activation_route_ids(request, routes_by_inventory)
    lot_size_route_ids = frozenset(
        route.route_id for route in request.routes if route.lot_size_shares is not None
    )
    tier_caps = _compute_tier_caps(request, config.elasticity)
    tiered_demand_group_ids = frozenset(tier_caps)

    tier_ids = [
        tier_scope_id(group_id, tier_index)
        for group_id, caps in tier_caps.items()
        for tier_index in range(len(caps))
    ]
    route_tier_ids = [
        route_tier_scope_id(route.route_id, tier_index)
        for route in request.routes
        if route.demand_group_id in tiered_demand_group_ids
        for tier_index in range(len(tier_caps[route.demand_group_id]))
    ]

    variable_index = build_variable_index(
        [
            ("q", [route.route_id for route in request.routes]),
            ("inc", [route.route_id for route in request.routes]),
            ("dec", [route.route_id for route in request.routes]),
            ("a", [inventory.inventory_id for inventory in request.inventory]),
            ("z", list(activation_route_ids)),
            ("n", list(lot_size_route_ids)),
            ("t", tier_ids),
            ("w", route_tier_ids),
        ]
    )
    return BuildContext(
        request=request,
        config=config,
        variable_index=variable_index,
        demand_caps=_compute_demand_caps(request, config.elasticity),
        inventory_by_id={inventory.inventory_id: inventory for inventory in request.inventory},
        routes_by_inventory=routes_by_inventory,
        routes_by_demand_group=_group_by(request.routes, key=lambda route: route.demand_group_id),
        routes_by_borrower=_group_by(request.routes, key=lambda route: route.borrower_id),
        activation_route_ids=activation_route_ids,
        lot_size_route_ids=lot_size_route_ids,
        tiered_demand_group_ids=tiered_demand_group_ids,
        tier_caps=tier_caps,
    )
