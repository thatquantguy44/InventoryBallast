"""Section 11.12's fee-revenue-net-of-variable-cost term:

    P_i(j) * q_j * tau * (f_j * s_j - c_j)

Reinvestment income (``r_j * h_j``) is a separate, optional term
(``objective_terms/reinvestment.py``, not yet built -- Section 28: "Cash collateral reinvestment:
Optional linear route economics, not a decision"). ``attribute()`` (T11) recomputes the same
per-route coefficient and multiplies it by the *solved* quantity, independent of the LP's own
compiled objective array (Section 18.2).
"""

from __future__ import annotations

from collections.abc import Sequence

from inventory_optimizer.components.decorators import objective_component
from inventory_optimizer.config.models import FormulationConfig
from inventory_optimizer.domain.enums import DayCountBasis, Formulation
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder
from inventory_optimizer.reporting.types import ObjectiveAttribution, VerifiedSolution

# Public (not module-private): specs/0010-multi-period-settlement/ reuses this same divisor map
# with a period-specific day count instead of `planning_horizon_days` -- one source of truth for
# what "act_360"/"act_365" mean, not a second copy.
DAY_COUNT_DIVISOR = {DayCountBasis.ACT_360: 360.0, DayCountBasis.ACT_365: 365.0}

COMPONENT_NAME = "fee_revenue"
COMPONENT_VERSION = "1"


def _day_count_fraction(formulation_config: FormulationConfig) -> float:
    divisor = DAY_COUNT_DIVISOR[formulation_config.day_count_basis]
    return formulation_config.planning_horizon_days / divisor


def fee_revenue_coefficient(
    route: LoanRoute,
    inventory: SecurityInventory,
    formulation_config: FormulationConfig,
    *,
    day_count_fraction: float | None = None,
) -> float:
    """The per-share ``q_j`` coefficient (Section 11.12). Shared by ``contribute()``,
    ``attribute()``, and ``reporting.explanations`` so all three agree on one formula rather than
    each re-deriving it.

    ``day_count_fraction`` (specs/0010-multi-period-settlement/ Phase 2, T-009) overrides the
    single-period ``tau`` derived from ``formulation_config.planning_horizon_days`` -- the joint
    multi-period LP's objective (``components.objective_terms.multi_period_economics``) needs a
    different, period-specific day-count fraction per period, but the price/fee/share/cost formula
    itself is unchanged. ``None`` (every existing call site) preserves today's exact behavior.
    """
    if day_count_fraction is None:
        tau = _day_count_fraction(formulation_config)
    else:
        tau = day_count_fraction
    return inventory.price_usd * tau * (
        route.fee_rate * route.revenue_share - route.variable_cost_rate
    )


@objective_component(
    name=COMPONENT_NAME,
    version=COMPONENT_VERSION,
    formulations={Formulation.LP, Formulation.MIP, Formulation.QP},
)
class FeeRevenueTerm:
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        for route in context.request.routes:
            inventory = context.inventory_by_id[route.inventory_id]
            coefficient = fee_revenue_coefficient(route, inventory, context.config.formulation)
            builder.add_objective_coefficient(VariableKey("q", route.route_id), coefficient)

    def attribute(self, solution: VerifiedSolution) -> ObjectiveAttribution:
        context = solution.context
        total = 0.0
        baseline = 0.0
        for route in context.request.routes:
            inventory = context.inventory_by_id[route.inventory_id]
            coefficient = fee_revenue_coefficient(route, inventory, context.config.formulation)
            q = solution.primal_at(VariableKey("q", route.route_id))
            total += coefficient * q
            baseline += coefficient * route.current_quantity_shares
        return ObjectiveAttribution(
            component_name=COMPONENT_NAME,
            component_version=COMPONENT_VERSION,
            unscaled_value_usd=total,
            baseline_value_usd=baseline,
            delta_usd=total - baseline,
        )
