"""Section 11.8: borrower notional/quantity caps.

    sum(P_i(j) * q_j for j in J(b)) <= K_b   (notional)
    sum(q_j for j in J(b))          <= K_b   (quantity)

Always included (``formulation.lp.REQUIRED_CONSTRAINTS``); a request with no
``CounterpartyLimit`` records contributes no rows.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence

from inventory_optimizer.components.decorators import constraint_component
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.policies import CounterpartyLimit
from inventory_optimizer.enrichment.entity_hierarchy import HierarchyResolutionStatus
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


def _limit_routes(limit: CounterpartyLimit, context: BuildContext) -> tuple[LoanRoute, ...]:
    if limit.ultimate_parent_id is not None:
        candidates = context.routes_by_ultimate_parent.get(limit.ultimate_parent_id, ())
    elif limit.legal_entity_id is not None:
        candidates = context.routes_by_entity.get(limit.legal_entity_id, ())
    else:
        candidates = context.routes_by_borrower.get(limit.borrower_id, ())
    return tuple(route for route in candidates if _in_scope(limit, route, context))


def _entity_scope(limit: CounterpartyLimit) -> tuple[str, str] | None:
    if limit.ultimate_parent_id is not None:
        return ("ultimate_parent_id", limit.ultimate_parent_id)
    if limit.legal_entity_id is not None:
        return ("legal_entity_id", limit.legal_entity_id)
    return None


def _issue_code(status: HierarchyResolutionStatus) -> str:
    if status is HierarchyResolutionStatus.LOW_CONFIDENCE:
        return "ENTITY_MAPPING_LOW_CONFIDENCE"
    if status is HierarchyResolutionStatus.CONFLICT:
        return "ENTITY_MAPPING_CONFLICT"
    return "ENTITY_MAPPING_UNRESOLVED"


@constraint_component(
    name="counterparty_limit",
    version="1",
    formulations={Formulation.LP, Formulation.MIP, Formulation.QP},
    hard=True,
)
class CounterpartyLimitConstraint:
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for limit_index, limit in enumerate(context.request.counterparty_limits):
            scope = _entity_scope(limit)
            if scope is None:
                continue
            scope_field, scope_id = scope
            matching_borrowers = {
                route.borrower_id
                for route in context.request.routes
                if _in_scope(limit, route, context)
                and (
                    (
                        scope_field == "legal_entity_id"
                        and context.entity_hierarchy_by_borrower[route.borrower_id].legal_entity_id
                        == scope_id
                    )
                    or (
                        scope_field == "ultimate_parent_id"
                        and context.entity_hierarchy_by_borrower[
                            route.borrower_id
                        ].ultimate_parent_id
                        == scope_id
                    )
                    or context.entity_hierarchy_by_borrower[route.borrower_id].status
                    is not HierarchyResolutionStatus.RESOLVED
                )
            }
            for borrower_id in sorted(matching_borrowers):
                resolution = context.entity_hierarchy_by_borrower[borrower_id]
                if resolution.status is HierarchyResolutionStatus.RESOLVED:
                    continue
                confidence = resolution.ownership_confidence
                if resolution.status is HierarchyResolutionStatus.LOW_CONFIDENCE:
                    reason = (
                        f"ownership_confidence {confidence!r} is below configured minimum "
                        f"{context.config.validation.minimum_entity_confidence!r}"
                    )
                else:
                    reason = resolution.status.value
                message = (
                    f"counterparty limit {limit.limit_id!r} scoped by {scope_field}={scope_id!r} "
                    f"cannot resolve borrower {borrower_id!r}: {reason}"
                )
                if limit.hard:
                    issues.append(
                        ValidationIssue(
                            code=_issue_code(resolution.status),
                            message=message,
                            location=f"counterparty_limits[{limit_index}].{scope_field}",
                        )
                    )
                else:
                    warnings.warn(message, RuntimeWarning, stacklevel=2)
        return tuple(issues)

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        for limit in context.request.counterparty_limits:
            routes = _limit_routes(limit, context)
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
