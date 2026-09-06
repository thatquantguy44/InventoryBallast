"""Section 12.4's discrete fee-tier pricing MIP (specs/0009-discrete-fee-tier-pricing/): for each
tiered demand group ``g`` with candidate fees ``k`` and routes ``j in J(g)``:

    tier_select[g]     :  sum_k z_gk <= 1
    tier_capacity[g,k] :  sum_{j in J(g)} w_jk - D_gk * z_gk <= 0
    tier_split[j]      :  q_j - sum_k w_jk = 0

Row (2) does double duty -- it caps quantity at the tier's own (elasticity-evaluated) demand *and*
forces every ``w_jk`` to zero whenever ``z_gk = 0``, so no separate big-M linking row is needed.
Row (1) is ``<=`` rather than ``=`` (spec.md's Assumptions, owner-confirmed 2026-09-05): a group
whose every tier is uneconomic simply goes unselected with every ``w_jk = 0``, which row (3) then
forces to ``q_j = 0`` -- "don't lend to this borrower at any offered price" stays feasible rather
than becoming infeasible.

Only ever contributed by ``formulation.mip.compile_mip`` (registered ``formulations={Formulation.
MIP}``); ``formulation.lp.compile_lp`` rejects any tiered request instead of silently ignoring
``candidate_fee_rates`` (``formulation.compiler_support.needs_mip``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from inventory_optimizer.components.decorators import constraint_component
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.context import (
    TIER_SEPARATOR,
    BuildContext,
    route_tier_scope_id,
    tier_scope_id,
)
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder

_FORMULATIONS = {Formulation.MIP}


@constraint_component(name="fee_tiers", version="1", formulations=_FORMULATIONS, hard=True)
class FeeTierConstraint:
    """Section 12.4's discrete price-selection structure. Route-level economics (Section 12.2:
    "Lender revenue shares may still produce different net route economics") are preserved by
    splitting each route's quantity across per-tier ``w_jk`` variables rather than valuing one
    group-level quantity -- see ``specs/0009-discrete-fee-tier-pricing/plan.md``'s recorded
    deviation from Section 12.4's literal ``q_gk`` sketch."""

    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        """REQ-008/AC-008: a route or demand-group id containing the reserved ``"#"`` separator
        would make the composite ``(route, tier)``/``(group, tier)`` variable keys
        ``formulation.context.build_context`` already built ambiguous. Caught here, before
        ``contribute()`` ever uses one of those keys, so an ambiguous key is rejected rather than
        silently solved against."""
        issues: list[ValidationIssue] = []
        for index, forecast in enumerate(context.request.demand):
            if not forecast.candidate_fee_rates:
                continue
            if TIER_SEPARATOR in forecast.demand_group_id:
                issues.append(
                    ValidationIssue(
                        code="RESERVED_SEPARATOR",
                        message=(
                            f"demand group {forecast.demand_group_id!r} contains the reserved "
                            f"fee-tier separator {TIER_SEPARATOR!r} -- rename the demand group"
                        ),
                        location=f"demand[{index}].demand_group_id",
                    )
                )
        for index, route in enumerate(context.request.routes):
            if route.demand_group_id not in context.tiered_demand_group_ids:
                continue
            if TIER_SEPARATOR in route.route_id:
                issues.append(
                    ValidationIssue(
                        code="RESERVED_SEPARATOR",
                        message=(
                            f"route {route.route_id!r} contains the reserved fee-tier separator "
                            f"{TIER_SEPARATOR!r} -- rename the route"
                        ),
                        location=f"routes[{index}].route_id",
                    )
                )
        return tuple(issues)

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        for group_id in context.tiered_demand_group_ids:
            caps = context.tier_caps[group_id]
            routes = context.routes_by_demand_group.get(group_id, ())

            select_row = builder.add_row("tier_select", group_id, lower=-math.inf, upper=1.0)

            for tier_index, evaluated in enumerate(caps):
                t_key = VariableKey("t", tier_scope_id(group_id, tier_index))
                builder.set_variable_bounds(t_key, lower=0.0, upper=1.0)
                builder.add_row_coefficient(select_row, t_key, 1.0)

                capacity_row = builder.add_row(
                    "tier_capacity",
                    tier_scope_id(group_id, tier_index),
                    lower=-math.inf,
                    upper=0.0,
                )
                builder.add_row_coefficient(capacity_row, t_key, -evaluated.effective_cap_shares)
                for route in routes:
                    w_key = VariableKey("w", route_tier_scope_id(route.route_id, tier_index))
                    builder.add_row_coefficient(capacity_row, w_key, 1.0)

            for route in routes:
                split_row = builder.add_row("tier_split", route.route_id, lower=0.0, upper=0.0)
                builder.add_row_coefficient(split_row, VariableKey("q", route.route_id), 1.0)
                for tier_index in range(len(caps)):
                    w_key = VariableKey("w", route_tier_scope_id(route.route_id, tier_index))
                    builder.add_row_coefficient(split_row, w_key, -1.0)
