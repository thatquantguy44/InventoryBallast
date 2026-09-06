"""Section 12.4's discrete fee-tier pricing revenue term (specs/0009-discrete-fee-tier-pricing/):
contributes only the *delta* between each candidate tier's revenue coefficient and the incumbent
``route.fee_rate``'s, applied to the per-route-per-tier ``w_jk`` variable
``components.constraints.fee_tiers.FeeTierConstraint`` introduces. ``fee_revenue`` itself stays
untouched (NFR-003):

    c_jk = P_i * tau * (f_gk * s_j - v_j)          # revenue coefficient at tier k
    delta_jk = c_jk - c_j^ref = P_i * tau * s_j * (f_gk - f_j^ref)

The ``variable_cost_rate`` term cancels identically, so this reuses ``fee_revenue``'s own
``fee_revenue_coefficient`` at a copy of the route repriced to the candidate fee, rather than
re-deriving the day-count/coefficient formula a second time -- one formula, two evaluations.
Because ``FeeTierConstraint``'s ``tier_split`` row guarantees ``sum_k w_jk = q_j``, the total of
``fee_revenue``'s unchanged ``c_j^ref * q_j`` plus this term's ``sum_k delta_jk * w_jk`` equals
Section 12.4's ``sum_k c_jk * w_jk`` exactly, route-by-route. ``attribute()`` recomputes the same
delta from primal ``w_jk`` values with ``baseline_value_usd = 0.0`` -- at the incumbent price the
delta is zero by construction, mirroring how ``transition_cost``/``allocation_stability`` already
report a zero baseline.
"""

from __future__ import annotations

from collections.abc import Sequence

from inventory_optimizer.components.decorators import objective_component
from inventory_optimizer.components.objective_terms.fee_revenue import fee_revenue_coefficient
from inventory_optimizer.config.models import FormulationConfig
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.context import BuildContext, route_tier_scope_id
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder
from inventory_optimizer.reporting.types import ObjectiveAttribution, VerifiedSolution

COMPONENT_NAME = "tier_pricing"
COMPONENT_VERSION = "1"


def _tier_delta_coefficient(
    route: LoanRoute,
    inventory: SecurityInventory,
    formulation_config: FormulationConfig,
    tier_fee: float,
) -> float:
    at_tier = route.model_copy(update={"fee_rate": tier_fee})
    return fee_revenue_coefficient(at_tier, inventory, formulation_config) - fee_revenue_coefficient(
        route, inventory, formulation_config
    )


@objective_component(
    name=COMPONENT_NAME,
    version=COMPONENT_VERSION,
    formulations={Formulation.MIP},
)
class TierPricingTerm:
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        formulation_config = context.config.formulation
        demand_by_group = {forecast.demand_group_id: forecast for forecast in context.request.demand}
        for group_id in context.tiered_demand_group_ids:
            forecast = demand_by_group[group_id]
            routes = context.routes_by_demand_group.get(group_id, ())
            for tier_index, tier_fee in enumerate(forecast.candidate_fee_rates):
                for route in routes:
                    inventory = context.inventory_by_id[route.inventory_id]
                    delta = _tier_delta_coefficient(route, inventory, formulation_config, tier_fee)
                    w_key = VariableKey("w", route_tier_scope_id(route.route_id, tier_index))
                    builder.add_objective_coefficient(w_key, delta)

    def attribute(self, solution: VerifiedSolution) -> ObjectiveAttribution:
        context = solution.context
        formulation_config = context.config.formulation
        demand_by_group = {forecast.demand_group_id: forecast for forecast in context.request.demand}
        total = 0.0
        for group_id in context.tiered_demand_group_ids:
            forecast = demand_by_group[group_id]
            routes = context.routes_by_demand_group.get(group_id, ())
            for tier_index, tier_fee in enumerate(forecast.candidate_fee_rates):
                for route in routes:
                    inventory = context.inventory_by_id[route.inventory_id]
                    delta = _tier_delta_coefficient(route, inventory, formulation_config, tier_fee)
                    w = solution.primal_at(
                        VariableKey("w", route_tier_scope_id(route.route_id, tier_index))
                    )
                    total += delta * w
        return ObjectiveAttribution(
            component_name=COMPONENT_NAME,
            component_version=COMPONENT_VERSION,
            unscaled_value_usd=total,
            baseline_value_usd=0.0,
            delta_usd=total,
        )
