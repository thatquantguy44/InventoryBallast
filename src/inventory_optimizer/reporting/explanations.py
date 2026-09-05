"""Decision explanations (T11; Section 18.3; VER-005).

For every route whose solved quantity materially differs from its current quantity, derive which
of the Section 18.3 ``ReasonCode`` values apply -- each from an independent, named predicate
evaluated against coefficients, row activity/slack, or upstream elasticity evidence, never from
generated prose (Section 18.3: "must not rely on generated prose to establish correctness").

Only the codes with an implemented upstream source are derived today:

- ``HIGHER_NET_FEE`` -- the route's fee-revenue coefficient is the (weak) maximum among the
  eligible routes sharing its inventory record (Section 11.4's shared balance row is where routes
  actually compete for scarce supply), i.e. it is the route the LP prefers to fill first.
- ``DEMAND_CAP_BINDING`` -- the route's demand-group ``demand_cap`` row has zero slack.
- ``ELASTICITY_REDUCED_DEMAND`` -- T06's elasticity service already flagged this exact code on the
  route's demand-group cap (``elasticity.EvaluatedDemand.reason_code``); this module only carries
  it through to the routes it affects rather than re-deriving it.

The remaining twenty-one codes are deferred to the constraint components that would supply their
evidence (utilization, reserve, counterparty, eligibility/collateral schedules, agency/prime) --
see ``specs/0002-result-attribution-explainability/tasks.md``'s Follow-ups.
"""

from __future__ import annotations

from inventory_optimizer.components.objective_terms.fee_revenue import fee_revenue_coefficient
from inventory_optimizer.domain.enums import ReasonCode
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.indexes import RowKey, VariableKey
from inventory_optimizer.reporting.types import RouteExplanation, VerifiedSolution
from inventory_optimizer.validation.solution_verifier import DEFAULT_TOLERANCE


def _route_coefficient(route: LoanRoute, context: BuildContext) -> float:
    inventory = context.inventory_by_id[route.inventory_id]
    return fee_revenue_coefficient(route, inventory, context.config.formulation)


def explain_routes(
    solution: VerifiedSolution, *, tolerance: float = DEFAULT_TOLERANCE
) -> tuple[RouteExplanation, ...]:
    if not solution.verification.has_primal:
        return ()

    context = solution.context
    problem = solution.problem
    assert solution.result.primal is not None  # guarded by has_primal above
    row_activity = problem.constraint_matrix @ solution.result.primal

    explanations: list[RouteExplanation] = []
    for route in context.request.routes:
        post_quantity = solution.primal_at(VariableKey("q", route.route_id))
        delta = post_quantity - route.current_quantity_shares
        if abs(delta) <= tolerance:
            continue

        reason_codes: list[ReasonCode] = []
        evidence: dict[str, float | str] = {"allocation_delta_shares": delta}

        if delta > tolerance:
            inventory_peers = context.routes_by_inventory.get(route.inventory_id, ())
            eligible_peers = [r for r in inventory_peers if r.eligible]
            if eligible_peers:
                route_coefficient = _route_coefficient(route, context)
                max_coefficient = max(
                    _route_coefficient(peer, context) for peer in eligible_peers
                )
                if route_coefficient >= max_coefficient - tolerance:
                    reason_codes.append(ReasonCode.HIGHER_NET_FEE)
                    evidence["net_fee_coefficient"] = route_coefficient

            try:
                row_position = problem.row_index.position(
                    RowKey("demand_cap", route.demand_group_id)
                )
            except KeyError:
                row_position = None
            if row_position is not None:
                slack = problem.row_upper[row_position] - row_activity[row_position]
                if slack <= tolerance:
                    reason_codes.append(ReasonCode.DEMAND_CAP_BINDING)
                    evidence["demand_cap_slack_shares"] = float(slack)

        evaluated_demand = context.demand_caps.get(route.demand_group_id)
        if (
            evaluated_demand is not None
            and evaluated_demand.reason_code is ReasonCode.ELASTICITY_REDUCED_DEMAND
        ):
            reason_codes.append(ReasonCode.ELASTICITY_REDUCED_DEMAND)
            evidence["effective_demand_cap_shares"] = evaluated_demand.effective_cap_shares

        if reason_codes:
            explanations.append(
                RouteExplanation(
                    route_id=route.route_id,
                    reason_codes=tuple(reason_codes),
                    evidence=evidence,
                )
            )

    return tuple(explanations)
