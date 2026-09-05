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
from inventory_optimizer.components.registry import ComponentKind
from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.domain.enums import Formulation, ObjectiveSense
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import InputValidationError, ValidationIssue
from inventory_optimizer.formulation.compiled import CompiledProblem
from inventory_optimizer.formulation.compiler_support import (
    mip_required_issues,
    qp_required_issues,
    resolve_component,
    set_route_bounds,
)
from inventory_optimizer.formulation.context import build_context
from inventory_optimizer.formulation.sparse_builder import SparseBuilder

REQUIRED_CONSTRAINTS: tuple[str, ...] = (
    "inventory_balance",
    "transition_identity",
    "demand_cap",
    "utilization_cap",
    "reserve_buffer",
    "counterparty_limit",
)
REQUIRED_OBJECTIVES: tuple[str, ...] = ("fee_revenue", "transition_cost")


def compile_lp(request: OptimizationRequest, config: InventoryOptimizerConfig) -> CompiledProblem:
    # Sections 14.1/14.2: fail closed rather than silently ignore all_or_none/lot_size_shares/
    # minimum_active_quantity_shares/maximum_active_routes (use formulation.mip.compile_mip) or a
    # positive allocation_stability_penalty (use formulation.qp.compile_qp) -- or
    # InventoryOptimizer.optimize(), which routes to either automatically.
    issues = mip_required_issues(request) + qp_required_issues(config)
    if issues:
        raise InputValidationError(issues)

    context = build_context(request, config)
    builder = SparseBuilder(context.variable_index)
    for route in request.routes:
        set_route_bounds(builder, route)

    all_names = (*REQUIRED_CONSTRAINTS, *REQUIRED_OBJECTIVES, *config.desk.enabled_components)
    component_names = list(dict.fromkeys(all_names))
    resolved = [resolve_component(name, formulation=Formulation.LP) for name in component_names]
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
