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

    variable_index = build_variable_index(
        [
            ("q", [route.route_id for route in request.routes]),
            ("inc", [route.route_id for route in request.routes]),
            ("dec", [route.route_id for route in request.routes]),
            ("a", [inventory.inventory_id for inventory in request.inventory]),
            ("z", list(activation_route_ids)),
            ("n", list(lot_size_route_ids)),
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
    )
