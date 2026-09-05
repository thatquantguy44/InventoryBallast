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
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from inventory_optimizer.config.models import ElasticityConfig, InventoryOptimizerConfig
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.loans import LoanRoute
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


def build_context(request: OptimizationRequest, config: InventoryOptimizerConfig) -> BuildContext:
    """Assemble a ``BuildContext`` from a request and config -- the same shape
    ``formulation.lp.compile_lp`` builds internally, exposed so any caller needing one (T12's
    facade, in order to build a ``reporting.types.VerifiedSolution``) does not have to duplicate or
    reach into another module's private helpers."""
    variable_index = build_variable_index(
        [
            ("q", [route.route_id for route in request.routes]),
            ("inc", [route.route_id for route in request.routes]),
            ("dec", [route.route_id for route in request.routes]),
            ("a", [inventory.inventory_id for inventory in request.inventory]),
        ]
    )
    return BuildContext(
        request=request,
        config=config,
        variable_index=variable_index,
        demand_caps=_compute_demand_caps(request, config.elasticity),
        inventory_by_id={inventory.inventory_id: inventory for inventory in request.inventory},
        routes_by_inventory=_group_by(request.routes, key=lambda route: route.inventory_id),
        routes_by_demand_group=_group_by(request.routes, key=lambda route: route.demand_group_id),
        routes_by_borrower=_group_by(request.routes, key=lambda route: route.borrower_id),
    )
