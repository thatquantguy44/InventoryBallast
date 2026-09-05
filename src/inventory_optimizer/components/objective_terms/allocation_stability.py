"""Section 14.2's allocation-stability convex QP term (T18; Phase 4): a per-route quadratic
penalty on quantity deviation from the current book, expressed entirely in terms of the existing
``inc``/``dec`` transition variables so it needs no new ``CompiledProblem`` field (no constant/
offset support exists anywhere in this engine, by design) and is exactly zero at the unchanged
baseline (``inc_j = dec_j = 0`` by the transition identity, mirroring
``objective_terms.transition_cost``'s own baseline-zero property).

``-(lambda/2) * (q_j - q0_j)^2 = -(lambda/2) * (inc_j - dec_j)^2`` (transition identity:
``q_j - q0_j = inc_j - dec_j``) expands to ``-(lambda/2)*inc_j^2 + lambda*inc_j*dec_j -
(lambda/2)*dec_j^2`` -- a 2x2 block per route with matrix ``[[lambda, -lambda], [-lambda,
lambda]]``, trivially positive semidefinite whenever ``lambda >= 0`` (eigenvalues ``0``,
``2*lambda``; already enforced by ``config.models.ObjectiveConfig``'s ``ge=0.0``).
``formulation.qp_support.signed_hessian``/``signed_quadratic_term`` apply this engine's
maximize-sense sign convention (Section 14.2: "QP matrices must be ... positive semidefinite";
the *contribution* to a maximized objective is the concave ``-0.5 * x^T Q x``, discouraging
deviation) once, centrally, for both the solver adapter and the independent verifier.
"""

from __future__ import annotations

from collections.abc import Sequence

from inventory_optimizer.components.decorators import objective_component
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder
from inventory_optimizer.reporting.types import ObjectiveAttribution, VerifiedSolution

COMPONENT_NAME = "allocation_stability"
COMPONENT_VERSION = "1"


@objective_component(
    name=COMPONENT_NAME,
    version=COMPONENT_VERSION,
    formulations={Formulation.QP},
)
class AllocationStabilityPenalty:
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        penalty = context.config.objective.allocation_stability_penalty
        for route in context.request.routes:
            inc_key = VariableKey("inc", route.route_id)
            dec_key = VariableKey("dec", route.route_id)
            builder.add_quadratic_objective_coefficient(inc_key, inc_key, penalty)
            builder.add_quadratic_objective_coefficient(dec_key, dec_key, penalty)
            builder.add_quadratic_objective_coefficient(inc_key, dec_key, -penalty)

    def attribute(self, solution: VerifiedSolution) -> ObjectiveAttribution:
        context = solution.context
        penalty = context.config.objective.allocation_stability_penalty
        total = 0.0
        for route in context.request.routes:
            inc = solution.primal_at(VariableKey("inc", route.route_id))
            dec = solution.primal_at(VariableKey("dec", route.route_id))
            total += -(penalty / 2.0) * (inc - dec) ** 2
        return ObjectiveAttribution(
            component_name=COMPONENT_NAME,
            component_version=COMPONENT_VERSION,
            unscaled_value_usd=total,
            baseline_value_usd=0.0,
            delta_usd=total,
        )
