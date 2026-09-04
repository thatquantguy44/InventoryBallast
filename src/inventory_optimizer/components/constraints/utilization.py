"""Section 11.7 (hard utilization floor/cap) and 11.9 (reserve buffer).

Both are always included (``formulation.lp.REQUIRED_CONSTRAINTS``); an inventory record with no
applicable ``UtilizationPolicy`` contributes nothing. Soft utilization-target deviations
(``d+_i``/``d-_i``) are not implemented -- Section 28's V0 default sets the target penalty to zero,
so there is nothing yet for a soft term to do.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from inventory_optimizer.components.decorators import constraint_component
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.policies import UtilizationPolicy
from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder

_FORMULATIONS = {Formulation.LP, Formulation.MIP, Formulation.QP}


def _policy_applies(policy: UtilizationPolicy, inventory: SecurityInventory) -> bool:
    if (
        policy.inventory_pool_id is not None
        and policy.inventory_pool_id != inventory.inventory_pool_id
    ):
        return False
    if policy.security_id is not None and policy.security_id != inventory.security_id:
        return False
    return True


@constraint_component(name="utilization_cap", version="1", formulations=_FORMULATIONS, hard=True)
class UtilizationCapConstraint:
    """``u_min_i * L_i <= O_i <= u_max_i * L_i`` where ``O_i = sum(q_j for j in J(i))``."""

    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        for inventory in context.request.inventory:
            routes = context.routes_by_inventory.get(inventory.inventory_id, ())
            for policy in context.request.utilization_policies:
                if not _policy_applies(policy, inventory):
                    continue
                total_lendable = inventory.total_lendable_shares
                if policy.maximum_utilization is not None:
                    row = builder.add_row(
                        "utilization_max",
                        f"{inventory.inventory_id}:{policy.policy_id}",
                        lower=-math.inf,
                        upper=policy.maximum_utilization * total_lendable,
                    )
                    for route in routes:
                        builder.add_row_coefficient(row, VariableKey("q", route.route_id), 1.0)
                if policy.minimum_utilization is not None:
                    row = builder.add_row(
                        "utilization_min",
                        f"{inventory.inventory_id}:{policy.policy_id}",
                        lower=policy.minimum_utilization * total_lendable,
                        upper=math.inf,
                    )
                    for route in routes:
                        builder.add_row_coefficient(row, VariableKey("q", route.route_id), 1.0)


@constraint_component(name="reserve_buffer", version="1", formulations=_FORMULATIONS, hard=True)
class ReserveBufferConstraint:
    """``a_i >= absolute_buffer_i`` and/or ``a_i >= buffer_fraction_i * L_i`` (Section 11.9),
    applied as a tightened lower bound on ``a_i`` rather than an extra row."""

    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        for inventory in context.request.inventory:
            buffer = 0.0
            for policy in context.request.utilization_policies:
                if not _policy_applies(policy, inventory):
                    continue
                buffer = max(
                    buffer,
                    policy.reserve_buffer_shares,
                    policy.reserve_buffer_fraction * inventory.total_lendable_shares,
                )
            if buffer > 0.0:
                builder.set_variable_bounds(
                    VariableKey("a", inventory.inventory_id), lower=buffer, upper=math.inf
                )
