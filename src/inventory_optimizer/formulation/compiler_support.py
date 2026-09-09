"""Shared compiler support (T15, T18): the resolve/route-bounds helpers ``formulation.lp.
compile_lp``, ``formulation.mip.compile_mip``, and ``formulation.qp.compile_qp`` all need, plus the
``needs_mip``/``needs_qp``/``*_required_issues``/``miqp_conflict_issues`` predicates used by each
compiler to fail closed (Sections 14.1, 14.2) and by ``facade.InventoryOptimizer`` to route
automatically -- extracted so no compiler reaches into another's internals, mirroring T12's own
``formulation.context.build_context`` extraction (a same-behavior move, not a rewrite).

``resolve_component`` requires the caller's target ``Formulation`` and rejects a resolved
component whose registered ``formulations`` metadata does not include it -- Section 15.1 says
components "declare formulations"; nothing enforced that declaration before T18, so a component
mistakenly added to ``config.desk.enabled_components`` for the wrong formulation would previously
be silently pulled in and could crash or misbehave at ``contribute()`` time instead of failing
clearly at resolution time. Every baseline/MIP component already declares its formulations
correctly and completely (verified via the full test suite), so this is purely additive for every
existing ``compile_lp``/``compile_mip`` call.
"""

from __future__ import annotations

from inventory_optimizer.components.registry import (
    ComponentKind,
    ComponentRegistration,
    default_registry,
)
from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import ConfigurationError, RegistrationError, ValidationIssue
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder

COMPONENT_VERSION = "1"


def resolve_component(
    name: str, *, formulation: Formulation, version: str = COMPONENT_VERSION
) -> tuple[ComponentKind, ComponentRegistration]:
    for kind in (ComponentKind.CONSTRAINT, ComponentKind.OBJECTIVE):
        try:
            registration = default_registry.get(kind, name, version)
        except RegistrationError:
            continue
        supported = registration.metadata.get("formulations", frozenset())
        if formulation not in supported:
            raise ConfigurationError(
                f"component {name!r} version {version!r} does not support formulation "
                f"{formulation.value!r} (declares {sorted(f.value for f in supported)}) -- check "
                "config.desk.enabled_components"
            )
        return kind, registration
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
    any route needs all-or-none/lot-size/minimum-ticket activation, any ``UtilizationPolicy`` sets
    a cardinality limit (``maximum_active_routes``), or any demand group carries candidate fee
    tiers (Section 12.4's discrete price-selection MIP; specs/0009-discrete-fee-tier-pricing/)."""
    if any(
        route.all_or_none
        or route.lot_size_shares is not None
        or route.minimum_active_quantity_shares is not None
        for route in request.routes
    ):
        return True
    if any(policy.maximum_active_routes is not None for policy in request.utilization_policies):
        return True
    return any(forecast.candidate_fee_rates for forecast in request.demand)


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
    for index, forecast in enumerate(request.demand):
        if forecast.candidate_fee_rates:
            issues.append(
                ValidationIssue(
                    code="MIP_REQUIRED",
                    message=(
                        f"demand group {forecast.demand_group_id!r} sets candidate_fee_rates, "
                        "which compile_lp cannot honor -- use compile_mip or "
                        "InventoryOptimizer.optimize()"
                    ),
                    location=f"demand[{index}].candidate_fee_rates",
                )
            )
    return tuple(issues)


def needs_qp(config: InventoryOptimizerConfig) -> bool:
    """Section 14.2: a desk-level policy decision (not a per-request trigger, unlike
    ``needs_mip``), since Phase 4's one QP term is a uniform stability coefficient, not a field on
    any individual route or policy. Zero (the field's default) means "no penalty configured" --
    every config that predates this field behaves identically."""
    return config.objective.allocation_stability_penalty > 0.0


def qp_required_issues(config: InventoryOptimizerConfig) -> tuple[ValidationIssue, ...]:
    if not needs_qp(config):
        return ()
    return (
        ValidationIssue(
            code="QP_REQUIRED",
            message=(
                "config.objective.allocation_stability_penalty is positive, which compile_lp "
                "cannot honor (no quadratic objective support) -- use compile_qp or "
                "InventoryOptimizer.optimize()"
            ),
            location="config.objective.allocation_stability_penalty",
        ),
    )


def miqp_conflict_issues() -> tuple[ValidationIssue, ...]:
    """Section 14.2: "Mixed-integer quadratic behavior requires a separate capable backend or an
    explicitly documented decomposition; it must never be labeled globally optimal when it is
    not." Neither exists yet, so a request needing both ``compile_mip``'s discrete triggers and
    ``compile_qp``'s configured stability penalty fails closed rather than silently picking one."""
    return (
        ValidationIssue(
            code="MIQP_UNSUPPORTED",
            message=(
                "combining a MIP-triggering route/policy with a positive "
                "allocation_stability_penalty is not supported in the same compile -- Section "
                "14.2 requires a separate capable backend or an explicitly documented "
                "decomposition for mixed-integer quadratic behavior; disable one trigger"
            ),
            location="request",
        ),
    )


def needs_multi_period(request: OptimizationRequest) -> bool:
    """specs/0010-multi-period-settlement/ Phase 2: a request opts into the joint multi-period LP
    purely by supplying ``planning_periods`` -- the same "strictly opt-in, empty means untouched"
    convention every other capability-gated extension in this repo already follows."""
    return bool(request.planning_periods)


def multi_period_conflict_issues(
    request: OptimizationRequest, config: InventoryOptimizerConfig
) -> tuple[ValidationIssue, ...]:
    """Phase 2's V1 is a pure continuous LP across periods -- combining ``planning_periods`` with
    any MIP trigger, a configured QP penalty, or a fee-tier menu is not supported in the same
    compile, mirroring exactly how MIP+QP already fails closed (``miqp_conflict_issues``) rather
    than silently dropping one capability. Every prior phase in this repo built its baseline
    before combining it with the next (LP before MIP, MIP before QP); this follows the same
    discipline instead of attempting all of them jointly at once."""
    if not needs_multi_period(request):
        return ()
    if needs_mip(request) or needs_qp(config):
        return (
            ValidationIssue(
                code="MULTI_PERIOD_MIP_QP_UNSUPPORTED",
                message=(
                    "combining planning_periods with a MIP-triggering route/policy, a fee-tier "
                    "menu, or a configured allocation_stability_penalty is not supported in the "
                    "same compile -- Section 22.11's joint multi-period LP is a pure continuous "
                    "LP for V1; disable one"
                ),
                location="request.planning_periods",
            ),
        )
    return ()
