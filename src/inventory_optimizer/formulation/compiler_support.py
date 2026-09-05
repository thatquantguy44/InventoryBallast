"""Shared compiler support (T15): the resolve/route-bounds helpers ``formulation.lp.compile_lp``
and ``formulation.mip.compile_mip`` both need, plus ``needs_mip``/``mip_required_issues`` (used by
``compile_lp`` to fail closed, Section 14.1, and by ``facade.InventoryOptimizer`` to route
automatically) -- extracted so neither compiler reaches into the other's internals, mirroring
T12's own ``formulation.context.build_context`` extraction (a same-behavior move, not a rewrite).
"""

from __future__ import annotations

from inventory_optimizer.components.registry import (
    ComponentKind,
    ComponentRegistration,
    default_registry,
)
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import RegistrationError, ValidationIssue
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder

COMPONENT_VERSION = "1"


def resolve_component(
    name: str, *, version: str = COMPONENT_VERSION
) -> tuple[ComponentKind, ComponentRegistration]:
    for kind in (ComponentKind.CONSTRAINT, ComponentKind.OBJECTIVE):
        try:
            return kind, default_registry.get(kind, name, version)
        except RegistrationError:
            continue
    raise RegistrationError(
        f"no constraint or objective component named {name!r} version {version!r}"
    )


def set_route_bounds(builder: SparseBuilder, route: LoanRoute) -> None:
    """Section 11.5 (route bounds) and 11.3 (transition change bounds).

    ``hard_minimum_quantity_shares`` is a contractual floor that eligibility does not remove; an
    ineligible route can only shrink toward it (grandfather), never grow. ``upper = max(upper,
    lower)`` guards against an already-below-floor current quantity inverting the bound -- schedule-
    driven grandfather/recall timing (Section 11.10) will replace this once T29 lands.
    """
    lower = route.hard_minimum_quantity_shares
    upper = (
        route.maximum_quantity_shares
        if route.eligible
        else min(route.maximum_quantity_shares, route.current_quantity_shares)
    )
    upper = max(upper, lower)
    builder.set_variable_bounds(VariableKey("q", route.route_id), lower=lower, upper=upper)

    inc_upper = max(upper - route.current_quantity_shares, 0.0)
    dec_upper = max(route.current_quantity_shares - lower, 0.0)
    builder.set_variable_bounds(VariableKey("inc", route.route_id), lower=0.0, upper=inc_upper)
    builder.set_variable_bounds(VariableKey("dec", route.route_id), lower=0.0, upper=dec_upper)


def needs_mip(request: OptimizationRequest) -> bool:
    """Section 14.1: "use MIP only when requested policy requires discrete variables." True when
    any route needs all-or-none/lot-size/minimum-ticket activation, or any ``UtilizationPolicy``
    sets a cardinality limit (``maximum_active_routes``)."""
    if any(
        route.all_or_none
        or route.lot_size_shares is not None
        or route.minimum_active_quantity_shares is not None
        for route in request.routes
    ):
        return True
    return any(policy.maximum_active_routes is not None for policy in request.utilization_policies)


def mip_required_issues(request: OptimizationRequest) -> tuple[ValidationIssue, ...]:
    """Every offending route/policy field, named individually -- Section 9.8's "aggregate every
    issue" convention, not just the first one found."""
    issues: list[ValidationIssue] = []
    for index, route in enumerate(request.routes):
        if route.all_or_none:
            issues.append(
                ValidationIssue(
                    code="MIP_REQUIRED",
                    message=(
                        f"route {route.route_id!r} sets all_or_none=True, which compile_lp "
                        "cannot honor -- use compile_mip or InventoryOptimizer.optimize()"
                    ),
                    location=f"routes[{index}].all_or_none",
                )
            )
        if route.lot_size_shares is not None:
            issues.append(
                ValidationIssue(
                    code="MIP_REQUIRED",
                    message=(
                        f"route {route.route_id!r} sets lot_size_shares, which compile_lp "
                        "cannot honor -- use compile_mip or InventoryOptimizer.optimize()"
                    ),
                    location=f"routes[{index}].lot_size_shares",
                )
            )
        if route.minimum_active_quantity_shares is not None:
            issues.append(
                ValidationIssue(
                    code="MIP_REQUIRED",
                    message=(
                        f"route {route.route_id!r} sets minimum_active_quantity_shares, which "
                        "compile_lp cannot honor -- use compile_mip or "
                        "InventoryOptimizer.optimize()"
                    ),
                    location=f"routes[{index}].minimum_active_quantity_shares",
                )
            )
    for index, policy in enumerate(request.utilization_policies):
        if policy.maximum_active_routes is not None:
            issues.append(
                ValidationIssue(
                    code="MIP_REQUIRED",
                    message=(
                        f"policy {policy.policy_id!r} sets maximum_active_routes, which "
                        "compile_lp cannot honor -- use compile_mip or "
                        "InventoryOptimizer.optimize()"
                    ),
                    location=f"utilization_policies[{index}].maximum_active_routes",
                )
            )
    return tuple(issues)
