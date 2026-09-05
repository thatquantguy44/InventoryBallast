"""Section 14.1 MIP business rules (T15): route activation (all-or-none, minimum ticket), route
cardinality, and integer lot sizes.

Only ever contributed by ``formulation.mip.compile_mip`` -- ``formulation.lp.compile_lp`` never
resolves these (registered with ``formulations={Formulation.MIP}``) and rejects any request that
would need them (``formulation.compiler_support.needs_mip``) rather than silently ignoring the
route/policy fields these components read.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from inventory_optimizer.components.constraints.utilization import _policy_applies
from inventory_optimizer.components.decorators import constraint_component
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder

_FORMULATIONS = {Formulation.MIP}


@constraint_component(name="route_activation", version="1", formulations=_FORMULATIONS, hard=True)
class RouteActivationConstraint:
    """One shared ``z`` binary per route in ``context.activation_route_ids``, linking it to ``q``
    per Section 14.1: ``all_or_none`` gets an equality (``q = max*z``, fully determining the link);
    everything else (minimum-ticket routes, and routes qualifying only because a cardinality policy
    counts them) gets the upper link (``q <= max*z``) that forces ``z=1`` whenever ``q > 0``, plus a
    lower link (``q >= min_ticket*z``) when a minimum ticket is set."""

    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        for route in context.request.routes:
            if route.route_id not in context.activation_route_ids:
                continue
            z_key = VariableKey("z", route.route_id)
            q_key = VariableKey("q", route.route_id)
            builder.set_variable_bounds(z_key, lower=0.0, upper=1.0)

            if route.all_or_none:
                row = builder.add_row("all_or_none", route.route_id, lower=0.0, upper=0.0)
                builder.add_row_coefficient(row, q_key, 1.0)
                builder.add_row_coefficient(row, z_key, -route.maximum_quantity_shares)
                continue

            if route.minimum_active_quantity_shares is not None:
                lower_row = builder.add_row(
                    "min_ticket", route.route_id, lower=0.0, upper=math.inf
                )
                builder.add_row_coefficient(lower_row, q_key, 1.0)
                builder.add_row_coefficient(
                    lower_row, z_key, -route.minimum_active_quantity_shares
                )

            upper_row = builder.add_row(
                "activation_upper", route.route_id, lower=-math.inf, upper=0.0
            )
            builder.add_row_coefficient(upper_row, q_key, 1.0)
            builder.add_row_coefficient(upper_row, z_key, -route.maximum_quantity_shares)


@constraint_component(name="cardinality", version="1", formulations=_FORMULATIONS, hard=True)
class CardinalityConstraint:
    """``sum(z_j for j in scope) <= maximum_active_routes`` per ``UtilizationPolicy`` (Section
    14.1's "maximum active route count"), scoped by inventory pool/security the same way
    ``UtilizationCapConstraint``/``ReserveBufferConstraint`` already are."""

    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        for policy in context.request.utilization_policies:
            if policy.maximum_active_routes is None:
                continue
            matching_routes = [
                route
                for inventory in context.request.inventory
                if _policy_applies(policy, inventory)
                for route in context.routes_by_inventory.get(inventory.inventory_id, ())
            ]
            if not matching_routes:
                continue
            row = builder.add_row(
                "cardinality",
                policy.policy_id,
                lower=-math.inf,
                upper=float(policy.maximum_active_routes),
            )
            for route in matching_routes:
                builder.add_row_coefficient(row, VariableKey("z", route.route_id), 1.0)


@constraint_component(name="lot_size", version="1", formulations=_FORMULATIONS, hard=True)
class LotSizeConstraint:
    """``q = lot_size * n`` with ``n`` a new non-negative integer variable (Section 14.1's "integer
    shares or lot multiples") for every route with ``lot_size_shares`` set."""

    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]:
        return ()

    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None:
        for route in context.request.routes:
            if route.lot_size_shares is None:
                continue
            lot_size = route.lot_size_shares
            q_key = VariableKey("q", route.route_id)
            n_key = VariableKey("n", route.route_id)

            row = builder.add_row("lot_size", route.route_id, lower=0.0, upper=0.0)
            builder.add_row_coefficient(row, q_key, 1.0)
            builder.add_row_coefficient(row, n_key, -lot_size)

            # Float-division guard: floor() on an exact ratio that lands a hair below an integer
            # (e.g. 100/25 as 3.9999999999) must not silently lose the top lot.
            max_n = math.floor(route.maximum_quantity_shares / lot_size + 1e-9)
            builder.set_variable_bounds(n_key, lower=0.0, upper=float(max_n))
