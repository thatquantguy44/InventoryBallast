"""Section 11.12's transition-cost term: ``-sum_j [k+_j * inc_j + k-_j * dec_j]``.

Expressed here as negative coefficients on ``inc_j``/``dec_j`` under a maximizing objective, which
is what makes both variables settle at zero unless the transition identity forces otherwise
(Section 11.3's degeneracy note). ``attribute()`` (T11) recomputes the same per-route cost against
the solved ``inc_j``/``dec_j`` values; at the unchanged baseline both are zero by the transition
identity (``q_j = q0_j`` implies ``inc_j = dec_j = 0``), so the baseline value is always zero.
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

COMPONENT_NAME = "transition_cost"
COMPONENT_VERSION = "1"


@objective_component(
    name=COMPONENT_NAME,
    version=COMPONENT_VERSION,
    formulations={Formulation.LP, Formulation.MIP, Formulation.QP},
)
class TransitionCostTerm:
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        for route in context.request.routes:
            builder.add_objective_coefficient(
                VariableKey("inc", route.route_id), -route.increase_cost_usd_per_share
            )
            builder.add_objective_coefficient(
                VariableKey("dec", route.route_id), -route.decrease_cost_usd_per_share
            )

    def attribute(self, solution: VerifiedSolution) -> ObjectiveAttribution:
        context = solution.context
        total = 0.0
        for route in context.request.routes:
            inc = solution.primal_at(VariableKey("inc", route.route_id))
            dec = solution.primal_at(VariableKey("dec", route.route_id))
            total += -(
                route.increase_cost_usd_per_share * inc + route.decrease_cost_usd_per_share * dec
            )
        return ObjectiveAttribution(
            component_name=COMPONENT_NAME,
            component_version=COMPONENT_VERSION,
            unscaled_value_usd=total,
            baseline_value_usd=0.0,
            delta_usd=total,
        )
