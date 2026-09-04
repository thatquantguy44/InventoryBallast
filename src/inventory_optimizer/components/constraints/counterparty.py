"""Section 11.8: borrower notional/quantity caps.

    sum(P_i(j) * q_j for j in J(b)) <= K_b   (notional)
    sum(q_j for j in J(b))          <= K_b   (quantity)

Always included (``formulation.lp.REQUIRED_CONSTRAINTS``); a request with no
``CounterpartyLimit`` records contributes no rows.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from inventory_optimizer.components.decorators import constraint_component
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.policies import CounterpartyLimit
from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder


def _in_scope(limit: CounterpartyLimit, route: LoanRoute, context: BuildContext) -> bool:
    if limit.security_id is not None and limit.security_id != route.security_id:
        return False
    if limit.inventory_pool_id is not None:
        inventory = context.inventory_by_id[route.inventory_id]
        if limit.inventory_pool_id != inventory.inventory_pool_id:
            return False
    return True


@constraint_component(
    name="counterparty_limit",
    version="1",
    formulations={Formulation.LP, Formulation.MIP, Formulation.QP},
    hard=True,
)
class CounterpartyLimitConstraint:
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        for limit in context.request.counterparty_limits:
            routes = [
                route
                for route in context.routes_by_borrower.get(limit.borrower_id, ())
                if _in_scope(limit, route, context)
            ]
            if not routes:
                continue

            if limit.maximum_quantity_shares is not None:
                row = builder.add_row(
                    "counterparty_quantity", limit.limit_id, lower=-math.inf,
                    upper=limit.maximum_quantity_shares,
                )
                for route in routes:
                    builder.add_row_coefficient(row, VariableKey("q", route.route_id), 1.0)

            if limit.maximum_notional_usd is not None:
                row = builder.add_row(
                    "counterparty_notional", limit.limit_id, lower=-math.inf,
                    upper=limit.maximum_notional_usd,
                )
                for route in routes:
                    price = context.inventory_by_id[route.inventory_id].price_usd
                    builder.add_row_coefficient(row, VariableKey("q", route.route_id), price)
