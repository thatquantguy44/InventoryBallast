"""Section 11.12's fee-revenue-net-of-variable-cost term:

    P_i(j) * q_j * tau * (f_j * s_j - c_j)

Reinvestment income (``r_j * h_j``) is a separate, optional term
(``objective_terms/reinvestment.py``, not yet built -- Section 28: "Cash collateral reinvestment:
Optional linear route economics, not a decision"). ``attribute()`` raises until T11 defines the
verified-solution shape it reconstructs from.
"""

from __future__ import annotations

from collections.abc import Sequence

from inventory_optimizer.components.decorators import objective_component
from inventory_optimizer.config.models import FormulationConfig
from inventory_optimizer.domain.enums import DayCountBasis, Formulation
from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder

_DAY_COUNT_DIVISOR = {DayCountBasis.ACT_360: 360.0, DayCountBasis.ACT_365: 365.0}


def _day_count_fraction(formulation_config: FormulationConfig) -> float:
    divisor = _DAY_COUNT_DIVISOR[formulation_config.day_count_basis]
    return formulation_config.planning_horizon_days / divisor


@objective_component(
    name="fee_revenue",
    version="1",
    formulations={Formulation.LP, Formulation.MIP, Formulation.QP},
)
class FeeRevenueTerm:
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        tau = _day_count_fraction(context.config.formulation)
        for route in context.request.routes:
            inventory = context.inventory_by_id[route.inventory_id]
            coefficient = inventory.price_usd * tau * (
                route.fee_rate * route.revenue_share - route.variable_cost_rate
            )
            builder.add_objective_coefficient(VariableKey("q", route.route_id), coefficient)

    def attribute(self, solution: object) -> object:
        raise NotImplementedError("objective attribution lands with T11")
