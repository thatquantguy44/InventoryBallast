"""Section 11.12's transition-cost term: ``-sum_j [k+_j * inc_j + k-_j * dec_j]``.

Expressed here as negative coefficients on ``inc_j``/``dec_j`` under a maximizing objective, which
is what makes both variables settle at zero unless the transition identity forces otherwise
(Section 11.3's degeneracy note).
"""

from __future__ import annotations

from collections.abc import Sequence

from inventory_optimizer.components.decorators import objective_component
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder


@objective_component(
    name="transition_cost",
    version="1",
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

    def attribute(self, solution: object) -> object:
        raise NotImplementedError("objective attribution lands with T11")
