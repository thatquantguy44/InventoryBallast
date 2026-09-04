"""Section 11.6: ``sum(q_j for j in J(g)) <= D_g``, using T06's elasticity-adjusted cap.

Always included (``formulation.lp.REQUIRED_CONSTRAINTS``); a demand group with no referencing
routes simply contributes no row.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from inventory_optimizer.components.decorators import constraint_component
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder


@constraint_component(
    name="demand_cap",
    version="1",
    formulations={Formulation.LP, Formulation.MIP, Formulation.QP},
    hard=True,
)
class DemandCapConstraint:
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        for forecast in context.request.demand:
            routes = context.routes_by_demand_group.get(forecast.demand_group_id, ())
            if not routes:
                continue
            cap = context.demand_caps[forecast.demand_group_id].effective_cap_shares
            row = builder.add_row(
                "demand_cap", forecast.demand_group_id, lower=-math.inf, upper=cap
            )
            for route in routes:
                builder.add_row_coefficient(row, VariableKey("q", route.route_id), 1.0)
