"""Baseline LP compiler (T08): turns a validated ``OptimizationRequest`` into a ``CompiledProblem``
using the Section 11 formulation and the registered component system (Section 15).

Deliberately not re-exported from ``formulation/__init__.py``: this module imports the concrete
component modules for their registration side effect, and those modules import
``formulation.context``/``formulation.sparse_builder`` -- keeping the compiler out of the package
``__init__`` avoids a dependency cycle between ``formulation`` and ``components`` at package-init
time. Import it directly: ``from inventory_optimizer.formulation.lp import compile_lp``.

``REQUIRED_CONSTRAINTS``/``REQUIRED_OBJECTIVES`` are the baseline family's fixed component set
(Section 11.3-11.9, 11.12); ``config.desk.enabled_components`` adds optional extras (e.g. a future
``reinvestment`` term). A richer "problem family declares its required components" mechanism is
deferred to the full desk-profile system (T35/CFG-004); hardcoding the baseline set here is
sufficient for the one family that exists today.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import TypeVar

# Importing these registers the baseline constraint/objective components (Section 15: registration
# happens at module import).
from inventory_optimizer.components.constraints import (
    counterparty as _counterparty,  # noqa: F401,E501
)
from inventory_optimizer.components.constraints import demand as _demand  # noqa: F401
from inventory_optimizer.components.constraints import (
    inventory_balance as _inventory_balance,  # noqa: F401,E501
)
from inventory_optimizer.components.constraints import utilization as _utilization  # noqa: F401
from inventory_optimizer.components.objective_terms import fee_revenue as _fee_revenue  # noqa: F401
from inventory_optimizer.components.objective_terms import (
    transition_cost as _transition_cost,  # noqa: F401,E501
)
from inventory_optimizer.components.registry import (
    ComponentKind,
    ComponentRegistration,
    default_registry,
)
from inventory_optimizer.config.models import ElasticityConfig, InventoryOptimizerConfig
from inventory_optimizer.domain.enums import Formulation, ObjectiveSense
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.elasticity import EvaluatedDemand, evaluate_demand_cap
from inventory_optimizer.exceptions import InputValidationError, RegistrationError, ValidationIssue
from inventory_optimizer.formulation.compiled import CompiledProblem
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder
from inventory_optimizer.formulation.variables import build_variable_index

REQUIRED_CONSTRAINTS: tuple[str, ...] = (
    "inventory_balance",
    "transition_identity",
    "demand_cap",
    "utilization_cap",
    "reserve_buffer",
    "counterparty_limit",
)
REQUIRED_OBJECTIVES: tuple[str, ...] = ("fee_revenue", "transition_cost")
_COMPONENT_VERSION = "1"

T = TypeVar("T")


def _group_by(items: Iterable[T], *, key: Callable[[T], str]) -> dict[str, tuple[T, ...]]:
    grouped: dict[str, list[T]] = defaultdict(list)
    for item in items:
        grouped[key(item)].append(item)
    return {group_key: tuple(values) for group_key, values in grouped.items()}


def _resolve_component(name: str) -> tuple[ComponentKind, ComponentRegistration]:
    for kind in (ComponentKind.CONSTRAINT, ComponentKind.OBJECTIVE):
        try:
            return kind, default_registry.get(kind, name, _COMPONENT_VERSION)
        except RegistrationError:
            continue
    raise RegistrationError(
        f"no constraint or objective component named {name!r} version {_COMPONENT_VERSION!r}"
    )


def _set_route_bounds(builder: SparseBuilder, route: LoanRoute) -> None:
    """Section 11.5 (route bounds) and 11.3 (transition change bounds).

    ``hard_minimum_quantity_shares`` is a contractual floor that eligibility does not remove; an
    ineligible route can only shrink toward it (grandfather), never grow. ``upper = max(upper,
    lower)`` guards against an already-below-floor current quantity inverting the bound -- schedule-
    driven grandfather/recall timing (Section 11.10) will replace this once T29 lands.
    """
    lower = route.hard_minimum_quantity_shares
    upper = (
        route.maximum_quantity_shares
        if route.eligible
        else min(route.maximum_quantity_shares, route.current_quantity_shares)
    )
    upper = max(upper, lower)
    builder.set_variable_bounds(VariableKey("q", route.route_id), lower=lower, upper=upper)

    inc_upper = max(upper - route.current_quantity_shares, 0.0)
    dec_upper = max(route.current_quantity_shares - lower, 0.0)
    builder.set_variable_bounds(VariableKey("inc", route.route_id), lower=0.0, upper=inc_upper)
    builder.set_variable_bounds(VariableKey("dec", route.route_id), lower=0.0, upper=dec_upper)


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


def compile_lp(request: OptimizationRequest, config: InventoryOptimizerConfig) -> CompiledProblem:
    variable_index = build_variable_index(
        [
            ("q", [route.route_id for route in request.routes]),
            ("inc", [route.route_id for route in request.routes]),
            ("dec", [route.route_id for route in request.routes]),
            ("a", [inventory.inventory_id for inventory in request.inventory]),
        ]
    )
    builder = SparseBuilder(variable_index)
    for route in request.routes:
        _set_route_bounds(builder, route)

    context = BuildContext(
        request=request,
        config=config,
        variable_index=variable_index,
        demand_caps=_compute_demand_caps(request, config.elasticity),
        inventory_by_id={inventory.inventory_id: inventory for inventory in request.inventory},
        routes_by_inventory=_group_by(request.routes, key=lambda route: route.inventory_id),
        routes_by_demand_group=_group_by(request.routes, key=lambda route: route.demand_group_id),
        routes_by_borrower=_group_by(request.routes, key=lambda route: route.borrower_id),
    )

    all_names = (*REQUIRED_CONSTRAINTS, *REQUIRED_OBJECTIVES, *config.desk.enabled_components)
    component_names = list(dict.fromkeys(all_names))
    resolved = [_resolve_component(name) for name in component_names]
    instances = [
        (kind, registration, registration.component_class())
        for kind, registration in resolved
    ]

    issues: list[ValidationIssue] = []
    for _, _, instance in instances:
        issues.extend(instance.validate(context))
    if issues:
        raise InputValidationError(tuple(issues))

    for kind, _, instance in instances:
        if kind is ComponentKind.CONSTRAINT:
            instance.contribute(context, builder)
    for kind, _, instance in instances:
        if kind is ComponentKind.OBJECTIVE:
            instance.contribute(context, builder)

    manifest = tuple(registration for _, registration, _ in instances)
    return builder.build(
        formulation=Formulation.LP,
        objective_sense=ObjectiveSense.MAXIMIZE,
        manifest=manifest,
    )
