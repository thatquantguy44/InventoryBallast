"""MIP compiler (T15; Section 14.1): reuses every baseline continuous constraint/objective
component unchanged (imported from ``formulation.lp``, which also registers them as an import side
effect -- this module does not re-import each one itself), adding the Phase 3 MIP-specific
components (``components.constraints.mip_rules``) and Section 12.4's discrete fee-tier pricing
components (``components.constraints.fee_tiers``, ``components.objective_terms.tier_pricing``;
specs/0009-discrete-fee-tier-pricing/) on top.

Deliberately not re-exported from ``formulation/__init__.py``, matching ``formulation.lp``'s own
convention and for the same reason: importing the concrete component modules for their
registration side effect would create a package-init-time cycle with ``components``.
"""

from __future__ import annotations

import numpy as np

# Importing these registers the MIP-specific components (Section 15: registration happens at
# module import).
from inventory_optimizer.components.constraints import fee_tiers as _fee_tiers  # noqa: F401
from inventory_optimizer.components.constraints import mip_rules as _mip_rules  # noqa: F401
from inventory_optimizer.components.objective_terms import (
    tier_pricing as _tier_pricing,  # noqa: F401
)
from inventory_optimizer.components.registry import ComponentKind
from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.domain.enums import Formulation, ObjectiveSense
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import InputValidationError, ValidationIssue
from inventory_optimizer.formulation.compiled import CompiledProblem
from inventory_optimizer.formulation.compiler_support import (
    miqp_conflict_issues,
    needs_qp,
    resolve_component,
    set_route_bounds,
)
from inventory_optimizer.formulation.context import build_context, tier_scope_id
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.lp import REQUIRED_CONSTRAINTS, REQUIRED_OBJECTIVES
from inventory_optimizer.formulation.sparse_builder import SparseBuilder

MIP_CONSTRAINTS: tuple[str, ...] = ("route_activation", "cardinality", "lot_size", "fee_tiers")
MIP_OBJECTIVES: tuple[str, ...] = ("tier_pricing",)


def compile_mip(request: OptimizationRequest, config: InventoryOptimizerConfig) -> CompiledProblem:
    if needs_qp(config):
        # Section 14.2: mixed-integer quadratic behavior needs a separate capable backend or an
        # explicitly documented decomposition -- neither exists yet, so fail closed rather than
        # silently dropping the configured stability penalty.
        raise InputValidationError(miqp_conflict_issues())

    context = build_context(request, config)
    builder = SparseBuilder(context.variable_index)
    for route in request.routes:
        set_route_bounds(builder, route)

    all_names = (
        *REQUIRED_CONSTRAINTS,
        *REQUIRED_OBJECTIVES,
        *MIP_CONSTRAINTS,
        *MIP_OBJECTIVES,
        *config.desk.enabled_components,
    )
    component_names = list(dict.fromkeys(all_names))
    resolved = [resolve_component(name, formulation=Formulation.MIP) for name in component_names]
    instances = [
        (kind, registration, registration.component_class()) for kind, registration in resolved
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

    integrality = np.zeros(len(context.variable_index), dtype=np.int8)
    for route_id in context.activation_route_ids:
        integrality[context.variable_index.position(VariableKey("z", route_id))] = 1
    for route_id in context.lot_size_route_ids:
        integrality[context.variable_index.position(VariableKey("n", route_id))] = 1
    for group_id, caps in context.tier_caps.items():
        for tier_index in range(len(caps)):
            t_key = VariableKey("t", tier_scope_id(group_id, tier_index))
            integrality[context.variable_index.position(t_key)] = 1

    return builder.build(
        formulation=Formulation.MIP,
        objective_sense=ObjectiveSense.MAXIMIZE,
        integrality=integrality,
        manifest=manifest,
    )
