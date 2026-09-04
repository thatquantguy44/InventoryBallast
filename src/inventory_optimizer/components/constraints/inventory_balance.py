"""Section 11.4 (hard inventory balance) and 11.3 (transition identity).

Both rows are always present in the baseline LP (``formulation.lp.REQUIRED_CONSTRAINTS``) -- they
are not policy-configurable; they define what "conserves shares" means for this problem family.
"""

from __future__ import annotations

from collections.abc import Sequence

from inventory_optimizer.components.decorators import constraint_component
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder

_FORMULATIONS = {Formulation.LP, Formulation.MIP, Formulation.QP}


@constraint_component(name="inventory_balance", version="1", formulations=_FORMULATIONS, hard=True)
class InventoryBalanceConstraint:
    """``sum(q_j for j in J(i)) + a_i = L_i - R_i - C_i`` (Section 11.4)."""

    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        for inventory in context.request.inventory:
            rhs = (
                inventory.total_lendable_shares
                - inventory.reserved_shares
                - inventory.committed_out_shares
            )
            row = builder.add_row(
                "inventory_balance", inventory.inventory_id, lower=rhs, upper=rhs
            )
            for route in context.routes_by_inventory.get(inventory.inventory_id, ()):
                builder.add_row_coefficient(row, VariableKey("q", route.route_id), 1.0)
            builder.add_row_coefficient(row, VariableKey("a", inventory.inventory_id), 1.0)


@constraint_component(
    name="transition_identity", version="1", formulations=_FORMULATIONS, hard=True
)
class TransitionIdentityConstraint:
    """``q_j - q0_j = inc_j - dec_j``, i.e. ``q_j - inc_j + dec_j = q0_j`` (Section 11.3)."""

    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        for route in context.request.routes:
            row = builder.add_row(
                "transition_identity",
                route.route_id,
                lower=route.current_quantity_shares,
                upper=route.current_quantity_shares,
            )
            builder.add_row_coefficient(row, VariableKey("q", route.route_id), 1.0)
            builder.add_row_coefficient(row, VariableKey("inc", route.route_id), -1.0)
            builder.add_row_coefficient(row, VariableKey("dec", route.route_id), 1.0)
