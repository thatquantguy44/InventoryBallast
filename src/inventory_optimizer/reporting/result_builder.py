"""Result assembly (T11; Section 18.1; VER-006).

``build_optimization_result`` is the single entry point that turns a ``VerifiedSolution`` into a
complete ``OptimizationResult`` -- the function T12's CLI/facade will call once it exists. Identity
fields the reporting layer has no business computing itself (``run_id``, ``created_at``,
``config_hash``, ``input_hash``, the platform envelope) are supplied by the caller, keeping this
function pure per NFR-004: no wall-clock read, no hashing, no I/O.

When there is no feasible primal (``VerificationReport.has_primal`` is false -- Section 16.3:
"results without a feasible primal vector do not produce allocation recommendations"),
allocation/balance/constraint/economics sections are empty rather than zero-filled placeholders.
"""

from __future__ import annotations

from pydantic import AwareDatetime

from inventory_optimizer.domain.results import (
    AllocationRecord,
    BalanceRecord,
    ConstraintActivity,
    DemandSummary,
    DeskSummary,
    EconomicsSummary,
    ObjectiveAttributionRecord,
    OptimizationResult,
    RowIdentifier,
    SolverDiagnostics,
    VerificationSection,
)
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.platform.context import PlatformInvocationContext
from inventory_optimizer.reporting.attribution import attribute_objective
from inventory_optimizer.reporting.explanations import explain_routes
from inventory_optimizer.reporting.shadow_prices import build_shadow_prices
from inventory_optimizer.reporting.types import VerifiedSolution
from inventory_optimizer.version import __version__ as PACKAGE_VERSION


def _build_allocations(solution: VerifiedSolution) -> tuple[AllocationRecord, ...]:
    if not solution.verification.has_primal:
        return ()

    context = solution.context
    explanations_by_route = {
        explanation.route_id: explanation for explanation in explain_routes(solution)
    }

    records: list[AllocationRecord] = []
    for route in context.request.routes:
        evaluated_demand = context.demand_caps.get(route.demand_group_id)
        explanation = explanations_by_route.get(route.route_id)
        records.append(
            AllocationRecord(
                route_id=route.route_id,
                inventory_id=route.inventory_id,
                demand_group_id=route.demand_group_id,
                current_quantity_shares=route.current_quantity_shares,
                post_quantity_shares=solution.primal_at(VariableKey("q", route.route_id)),
                increase_shares=solution.primal_at(VariableKey("inc", route.route_id)),
                decrease_shares=solution.primal_at(VariableKey("dec", route.route_id)),
                fee_rate=route.fee_rate,
                demand_cap_shares=(
                    evaluated_demand.effective_cap_shares if evaluated_demand else None
                ),
                eligible=route.eligible,
                reason_codes=explanation.reason_codes if explanation else (),
                explanation_evidence=explanation.evidence if explanation else {},
            )
        )
    return tuple(records)


def _build_balances(solution: VerifiedSolution) -> tuple[BalanceRecord, ...]:
    if not solution.verification.has_primal:
        return ()

    context = solution.context
    records: list[BalanceRecord] = []
    for inventory in context.request.inventory:
        routes = context.routes_by_inventory.get(inventory.inventory_id, ())
        post_on_loan = sum(
            solution.primal_at(VariableKey("q", route.route_id)) for route in routes
        )
        utilization = (
            post_on_loan / inventory.total_lendable_shares
            if inventory.total_lendable_shares > 0
            else 0.0
        )
        records.append(
            BalanceRecord(
                inventory_id=inventory.inventory_id,
                pre_total_lendable_shares=inventory.total_lendable_shares,
                pre_reserved_shares=inventory.reserved_shares,
                pre_committed_out_shares=inventory.committed_out_shares,
                pre_on_loan_shares=inventory.on_loan_shares,
                pre_available_to_lend_shares=inventory.available_to_lend_shares,
                post_available_shares=solution.primal_at(
                    VariableKey("a", inventory.inventory_id)
                ),
                post_on_loan_shares=post_on_loan,
                utilization=utilization,
            )
        )
    return tuple(records)


def _build_economics(solution: VerifiedSolution) -> EconomicsSummary:
    if not solution.verification.has_primal:
        return EconomicsSummary(components=(), total_value_usd=0.0, total_delta_usd=0.0)

    attributions = attribute_objective(solution)
    components = tuple(
        ObjectiveAttributionRecord(
            component_name=attribution.component_name,
            component_version=attribution.component_version,
            unscaled_value_usd=attribution.unscaled_value_usd,
            baseline_value_usd=attribution.baseline_value_usd,
            delta_usd=attribution.delta_usd,
        )
        for attribution in attributions
    )
    return EconomicsSummary(
        components=components,
        total_value_usd=sum(a.unscaled_value_usd for a in attributions),
        total_delta_usd=sum(a.delta_usd for a in attributions),
    )


def _build_demand(solution: VerifiedSolution) -> tuple[DemandSummary, ...]:
    context = solution.context
    records: list[DemandSummary] = []
    for forecast in context.request.demand:
        evaluated = context.demand_caps.get(forecast.demand_group_id)
        routes = context.routes_by_demand_group.get(forecast.demand_group_id, ())
        filled = sum(solution.primal_at(VariableKey("q", route.route_id)) for route in routes)
        effective_cap = (
            evaluated.effective_cap_shares if evaluated else forecast.reference_quantity_shares
        )
        records.append(
            DemandSummary(
                demand_group_id=forecast.demand_group_id,
                reference_quantity_shares=forecast.reference_quantity_shares,
                raw_demand_shares=(
                    evaluated.raw_demand_shares if evaluated else forecast.reference_quantity_shares
                ),
                effective_cap_shares=effective_cap,
                filled_shares=filled,
                unfilled_shares=max(effective_cap - filled, 0.0),
                fill_ratio=(filled / effective_cap) if effective_cap > 0 else 0.0,
                reason_code=evaluated.reason_code if evaluated else None,
            )
        )
    return tuple(records)


def _build_desk(solution: VerifiedSolution) -> DeskSummary:
    context = solution.context
    desk_context = context.request.desk_context
    return DeskSummary(
        problem_family=(
            desk_context.problem_family if desk_context else context.request.problem_family
        ),
        legal_entity_id=desk_context.legal_entity_id if desk_context else None,
        platform_tenant_id=desk_context.platform_tenant_id if desk_context else None,
        attribution_scope=desk_context.attribution_scope if desk_context else None,
        enabled_components=context.config.desk.enabled_components,
    )


def _build_constraints(solution: VerifiedSolution) -> tuple[ConstraintActivity, ...]:
    if not solution.verification.has_primal:
        return ()
    assert solution.result.primal is not None  # guarded by has_primal above

    problem = solution.problem
    row_activity = problem.constraint_matrix @ solution.result.primal
    duals_by_row = {entry.row_key: entry.dual_value for entry in build_shadow_prices(solution)}

    records: list[ConstraintActivity] = []
    for position, row_key in enumerate(problem.row_index.keys):
        lower = float(problem.row_lower[position])
        upper = float(problem.row_upper[position])
        activity = float(row_activity[position])
        records.append(
            ConstraintActivity(
                row=RowIdentifier(kind=row_key.kind, scope_id=row_key.scope_id),
                lower=lower,
                upper=upper,
                activity=activity,
                slack=min(activity - lower, upper - activity),
                dual_value=duals_by_row.get(row_key),
            )
        )
    return tuple(records)


def _build_solver_diagnostics(solution: VerifiedSolution) -> SolverDiagnostics:
    result = solution.result
    return SolverDiagnostics(
        backend_name=result.backend_name,
        backend_version=result.backend_version,
        runtime_seconds=result.runtime_seconds,
        iterations=result.iterations,
        nodes=result.nodes,
        best_bound=result.best_bound,
        relative_gap=result.relative_gap,
        termination_reason=result.termination_reason,
    )


def _build_verification_section(solution: VerifiedSolution) -> VerificationSection:
    verification = solution.verification
    return VerificationSection(
        has_primal=verification.has_primal,
        max_variable_bound_violation=verification.max_variable_bound_violation,
        max_row_violation=verification.max_row_violation,
        max_integrality_violation=verification.max_integrality_violation,
        objective_reconstruction_delta=verification.objective_reconstruction_delta,
        passed=verification.passed,
    )


def _build_warnings(solution: VerifiedSolution) -> tuple[str, ...]:
    warnings: list[str] = []
    if not solution.verification.has_primal:
        warnings.append("no feasible primal returned; no allocation recommendation is produced")
    elif not solution.verification.passed:
        warnings.append("independent verification failed; result should not be trusted as-is")
    if solution.result.dual is None:
        warnings.append("no LP duals available; shadow prices are not reported for this solve")
    return tuple(warnings)


def build_optimization_result(
    solution: VerifiedSolution,
    *,
    run_id: str,
    created_at: AwareDatetime,
    config_hash: str,
    input_hash: str,
    platform: PlatformInvocationContext | None = None,
) -> OptimizationResult:
    result = solution.result
    return OptimizationResult(
        request_id=solution.context.request.request_id,
        run_id=run_id,
        created_at=created_at,
        config_hash=config_hash,
        input_hash=input_hash,
        package_version=PACKAGE_VERSION,
        backend_version=result.backend_version,
        status=result.status,
        native_status=result.native_status,
        strict=True,
        termination_reason=result.termination_reason,
        allocations=_build_allocations(solution),
        balances=_build_balances(solution),
        economics=_build_economics(solution),
        demand=_build_demand(solution),
        desk=_build_desk(solution),
        constraints=_build_constraints(solution),
        solver=_build_solver_diagnostics(solution),
        verification=_build_verification_section(solution),
        warnings=_build_warnings(solution),
        platform=platform,
    )
