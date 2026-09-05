"""QP compiler (T18; Section 14.2): reuses every baseline continuous constraint/objective
component unchanged (imported from ``formulation.lp``, which also registers them as an import side
effect -- this module does not re-import each one itself), adding the one Phase 4 convex QP
objective term (``components.objective_terms.allocation_stability``) on top. Mirrors
``formulation.mip.compile_mip``'s own structure almost exactly.

Deliberately not re-exported from ``formulation/__init__.py``, matching ``formulation.lp``'s own
convention and for the same reason: importing the concrete component modules for their
registration side effect would create a package-init-time cycle with ``components``.

Also computes ``CompiledProblem.scaling`` (Section 20.3) whenever a quadratic term exists: HiGHS's
QP solver was empirically found to stall on small Hessian magnitudes relative to the rest of the
model (see ``solvers.highs``'s module docstring for the full account) -- ``objective_scale_usd`` is
set so the assembled Hessian's largest-magnitude entry becomes exactly ``1.0``, a value only
``solvers.highs`` ever reads; ``linear_objective``/``quadratic_objective`` themselves are left
untouched (still true USD units), so every other consumer of this ``CompiledProblem`` (the
independent verifier, attribution) needs no scaling awareness at all.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from inventory_optimizer.components.objective_terms import (
    allocation_stability as _allocation_stability,  # noqa: F401
)
from inventory_optimizer.components.registry import ComponentKind
from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.domain.enums import Formulation, ObjectiveSense
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import InputValidationError, ValidationIssue
from inventory_optimizer.formulation.compiled import CompiledProblem, ScalingMetadata, SparseMatrix
from inventory_optimizer.formulation.compiler_support import (
    miqp_conflict_issues,
    needs_mip,
    resolve_component,
    set_route_bounds,
)
from inventory_optimizer.formulation.context import build_context
from inventory_optimizer.formulation.lp import REQUIRED_CONSTRAINTS, REQUIRED_OBJECTIVES
from inventory_optimizer.formulation.qp_support import validate_psd
from inventory_optimizer.formulation.sparse_builder import SparseBuilder

QP_OBJECTIVES: tuple[str, ...] = ("allocation_stability",)


def _objective_scaling(matrix: SparseMatrix) -> ScalingMetadata:
    max_abs = float(np.max(np.abs(matrix.data))) if matrix.nnz else 0.0
    if max_abs <= 0.0:
        return ScalingMetadata()
    return ScalingMetadata(applied=True, objective_scale_usd=1.0 / max_abs)


def compile_qp(request: OptimizationRequest, config: InventoryOptimizerConfig) -> CompiledProblem:
    if needs_mip(request):
        # Section 14.2: mixed-integer quadratic behavior needs a separate capable backend or an
        # explicitly documented decomposition -- neither exists yet, so fail closed rather than
        # silently dropping either the discrete triggers or the quadratic penalty.
        raise InputValidationError(miqp_conflict_issues())

    context = build_context(request, config)
    builder = SparseBuilder(context.variable_index)
    for route in request.routes:
        set_route_bounds(builder, route)

    all_names = (
        *REQUIRED_CONSTRAINTS,
        *REQUIRED_OBJECTIVES,
        *QP_OBJECTIVES,
        *config.desk.enabled_components,
    )
    component_names = list(dict.fromkeys(all_names))
    resolved = [resolve_component(name, formulation=Formulation.QP) for name in component_names]
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
    problem = builder.build(
        formulation=Formulation.QP,
        objective_sense=ObjectiveSense.MAXIMIZE,
        manifest=manifest,
    )

    if problem.quadratic_objective is not None:
        psd_issues = validate_psd(problem.quadratic_objective)
        if psd_issues:
            raise InputValidationError(psd_issues)
        scaling = _objective_scaling(problem.quadratic_objective)
        problem = dataclasses.replace(problem, scaling=scaling)

    return problem
