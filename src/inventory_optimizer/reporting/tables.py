"""Tabular projections of the public result types (T-002/T-003; Section 7.1: ``reporting`` owns
"Tables, attribution, serialization"; Section 7's package tree names this module).

Pure and dependency-free: ``domain`` plus the standard library, no pandas, no I/O. Converting a
``Table`` into a CSV file or a DataFrame belongs to ``adapters`` (Section 7.1: "JSON and optional
dataframe conversion"), which is what keeps the optional ``dataframe`` extra at the boundary
instead of making every caller who wants a CSV depend on pandas.

Every cell projects a field that already exists on the result object. Nothing here recomputes an
objective, re-solves, or derives a new metric -- Section 7.1 forbids ``reporting`` from "re-solving
or changing results", and a derived measure invented in a formatting layer would be analytical
policy hiding in the wrong place.

Table names and column order are a **contract** (``specs/0008-tabular-result-output/`` NFR-003):
CSV and DataFrame consumers index by them, so changing one is a breaking change, not a rename.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias

from inventory_optimizer.domain.results import OptimizationResult
from inventory_optimizer.domain.scenario_results import ScenarioComparison, StressTestReport

Cell: TypeAlias = str | float | int | bool | None

_JOIN = "|"


class RunSummaryLayout(StrEnum):
    """Which shape ``run_summary`` takes (REQ-012).

    ``WIDE`` is one row whose columns are the summary fields -- a single run pasted into a
    spreadsheet. ``LONG`` is one row per field, carrying ``run_id`` so many runs concatenate into
    one frame for cross-run comparison. Neither serves both, so the caller picks; the long table is
    *derived* from the wide one, so the two cannot drift apart.

    A module-local enum rather than a ``domain.enums`` addition: this is a presentation option, not
    a business concept (Section 7.1 gives ``domain`` "business records, IDs, enums"), following
    ``components.registry.ComponentKind``'s precedent for infrastructure enums living beside their
    own code.
    """

    WIDE = "wide"
    LONG = "long"


@dataclass(frozen=True, slots=True)
class Table:
    """One named, ordered projection. Frozen and slotted like every other internal record here
    (``VariableKey``, ``ScalingMetadata``, ``VerificationReport``) -- deliberately not a Pydantic
    model, since the validated boundary contract is ``OptimizationResult`` upstream, not this."""

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Cell, ...], ...]


def _enum(value: StrEnum | None) -> str | None:
    return None if value is None else value.value


def _joined_enums(values: Sequence[StrEnum]) -> str:
    return _JOIN.join(v.value for v in values)


def _joined(values: Sequence[str]) -> str:
    return _JOIN.join(values)


def _isoformat(value: datetime) -> str:
    return value.isoformat()


# --------------------------------------------------------------------------------------
# OptimizationResult
# --------------------------------------------------------------------------------------

_ALLOCATION_COLUMNS = (
    "route_id",
    "inventory_id",
    "demand_group_id",
    "current_quantity_shares",
    "post_quantity_shares",
    "increase_shares",
    "decrease_shares",
    "fee_rate",
    "demand_cap_shares",
    "eligible",
    "reason_codes",
)


def allocations_table(result: OptimizationResult) -> Table:
    rows = tuple(
        (
            a.route_id,
            a.inventory_id,
            a.demand_group_id,
            a.current_quantity_shares,
            a.post_quantity_shares,
            a.increase_shares,
            a.decrease_shares,
            a.fee_rate,
            a.demand_cap_shares,
            a.eligible,
            _joined_enums(a.reason_codes),
        )
        for a in result.allocations
    )
    return Table(name="allocations", columns=_ALLOCATION_COLUMNS, rows=rows)


def allocation_evidence_table(result: OptimizationResult) -> Table:
    """Long format, one row per evidence entry (RISK-002). ``explanation_evidence`` is a free-form
    mapping whose keys vary with which reason codes fired, so flattening it into columns would give
    a schema that changes run to run; long format keeps a fixed schema whatever the keys are. Keys
    are sorted so repeated runs are byte-identical (REQ-009)."""
    rows: list[tuple[Cell, ...]] = []
    for allocation in result.allocations:
        evidence: Mapping[str, float | str] = allocation.explanation_evidence
        for key in sorted(evidence):
            rows.append((allocation.route_id, key, str(evidence[key])))
    return Table(
        name="allocation_evidence", columns=("route_id", "key", "value"), rows=tuple(rows)
    )


_BALANCE_COLUMNS = (
    "inventory_id",
    "pre_total_lendable_shares",
    "pre_reserved_shares",
    "pre_committed_out_shares",
    "pre_on_loan_shares",
    "pre_available_to_lend_shares",
    "post_available_shares",
    "post_on_loan_shares",
    "utilization",
)


def balances_table(result: OptimizationResult) -> Table:
    rows = tuple(
        (
            b.inventory_id,
            b.pre_total_lendable_shares,
            b.pre_reserved_shares,
            b.pre_committed_out_shares,
            b.pre_on_loan_shares,
            b.pre_available_to_lend_shares,
            b.post_available_shares,
            b.post_on_loan_shares,
            b.utilization,
        )
        for b in result.balances
    )
    return Table(name="balances", columns=_BALANCE_COLUMNS, rows=rows)


_DEMAND_COLUMNS = (
    "demand_group_id",
    "reference_quantity_shares",
    "raw_demand_shares",
    "effective_cap_shares",
    "filled_shares",
    "unfilled_shares",
    "fill_ratio",
    "reason_code",
)


def demand_table(result: OptimizationResult) -> Table:
    rows = tuple(
        (
            d.demand_group_id,
            d.reference_quantity_shares,
            d.raw_demand_shares,
            d.effective_cap_shares,
            d.filled_shares,
            d.unfilled_shares,
            d.fill_ratio,
            _enum(d.reason_code),
        )
        for d in result.demand
    )
    return Table(name="demand", columns=_DEMAND_COLUMNS, rows=rows)


_CONSTRAINT_COLUMNS = (
    "row_kind",
    "row_scope_id",
    "lower",
    "upper",
    "activity",
    "slack",
    "dual_value",
)


def constraints_table(result: OptimizationResult) -> Table:
    rows = tuple(
        (c.row.kind, c.row.scope_id, c.lower, c.upper, c.activity, c.slack, c.dual_value)
        for c in result.constraints
    )
    return Table(name="constraints", columns=_CONSTRAINT_COLUMNS, rows=rows)


_ECONOMICS_COLUMNS = (
    "component_name",
    "component_version",
    "unscaled_value_usd",
    "baseline_value_usd",
    "delta_usd",
)


def economics_table(result: OptimizationResult) -> Table:
    """One row per objective component. The totals live in ``run_summary`` rather than as an
    appended TOTAL row, which would mix grains in one table and break any downstream ``sum()``."""
    rows = tuple(
        (
            c.component_name,
            c.component_version,
            c.unscaled_value_usd,
            c.baseline_value_usd,
            c.delta_usd,
        )
        for c in result.economics.components
    )
    return Table(name="economics", columns=_ECONOMICS_COLUMNS, rows=rows)


_RUN_SUMMARY_COLUMNS = (
    "request_id",
    "run_id",
    "created_at",
    "config_hash",
    "input_hash",
    "package_version",
    "backend_version",
    "status",
    "native_status",
    "strict",
    "termination_reason",
    "objective_total_value_usd",
    "objective_total_delta_usd",
    "solver_backend_name",
    "solver_backend_version",
    "solver_runtime_seconds",
    "solver_iterations",
    "solver_nodes",
    "solver_best_bound",
    "solver_relative_gap",
    "solver_termination_reason",
    "verification_has_primal",
    "verification_max_variable_bound_violation",
    "verification_max_row_violation",
    "verification_max_integrality_violation",
    "verification_objective_reconstruction_delta",
    "verification_passed",
    "desk_problem_family",
    "desk_legal_entity_id",
    "desk_platform_tenant_id",
    "desk_attribution_scope",
    "warnings",
)


def run_summary_table(result: OptimizationResult) -> Table:
    """Exactly one row. ``desk`` is optional on the result, so its four columns are ``None`` when
    absent -- the row's width never varies."""
    desk = result.desk
    row: tuple[Cell, ...] = (
        result.request_id,
        result.run_id,
        _isoformat(result.created_at),
        result.config_hash,
        result.input_hash,
        result.package_version,
        result.backend_version,
        result.status.value,
        result.native_status,
        result.strict,
        result.termination_reason,
        result.economics.total_value_usd,
        result.economics.total_delta_usd,
        result.solver.backend_name,
        result.solver.backend_version,
        result.solver.runtime_seconds,
        result.solver.iterations,
        result.solver.nodes,
        result.solver.best_bound,
        result.solver.relative_gap,
        result.solver.termination_reason,
        result.verification.has_primal,
        result.verification.max_variable_bound_violation,
        result.verification.max_row_violation,
        result.verification.max_integrality_violation,
        result.verification.objective_reconstruction_delta,
        result.verification.passed,
        None if desk is None else desk.problem_family.value,
        None if desk is None else desk.legal_entity_id,
        None if desk is None else desk.platform_tenant_id,
        None if desk is None else desk.attribution_scope,
        _joined(result.warnings),
    )
    return Table(name="run_summary", columns=_RUN_SUMMARY_COLUMNS, rows=(row,))


def run_summary_long_table(result: OptimizationResult) -> Table:
    """The wide summary transposed to ``run_id``/``key``/``value`` pairs (REQ-012).

    Derived from ``run_summary_table`` rather than a second field list, so adding a summary field
    reaches both shapes automatically and they cannot disagree. Key order equals the wide column
    order -- related fields stay adjacent, and the two layouts read the same way top-to-bottom vs.
    left-to-right. ``run_id`` repeats on every row (ordinary tidy-data practice), which is what
    makes concatenating many runs' long tables unambiguous.

    Trade-off: every value shares one column, so per-column dtype is lost (a DataFrame gets
    ``object``, a CSV consumer casts on read). That is why ``WIDE`` remains the default.
    """
    wide = run_summary_table(result)
    (row,) = wide.rows
    rows = tuple(
        (result.run_id, column, cell)
        for column, cell in zip(wide.columns, row, strict=True)  # 1:1 or the derivation is broken
    )
    return Table(name="run_summary_long", columns=("run_id", "key", "value"), rows=rows)


def result_tables(
    result: OptimizationResult,
    *,
    run_summary_layout: RunSummaryLayout = RunSummaryLayout.WIDE,
) -> tuple[Table, ...]:
    """Every table for one ``OptimizationResult``, in the documented order (REQ-004).

    ``schedules``/``collateral``/``sources`` get no tables: they are always ``None`` today (no
    upstream domain model exists yet -- see ``VER-006``'s own status note). Adding them later is
    additive.
    """
    summary = (
        run_summary_long_table(result)
        if run_summary_layout is RunSummaryLayout.LONG
        else run_summary_table(result)
    )
    return (
        allocations_table(result),
        allocation_evidence_table(result),
        balances_table(result),
        demand_table(result),
        constraints_table(result),
        economics_table(result),
        summary,
    )


# --------------------------------------------------------------------------------------
# ScenarioComparison
# --------------------------------------------------------------------------------------

_SCENARIO_SUMMARY_COLUMNS = (
    "scenario_id",
    "scenario_name",
    "baseline_run_id",
    "scenario_run_id",
    "status",
    "verification_passed",
    "objective_delta_usd",
    "unfilled_demand_delta_shares",
    "config_hash",
    "baseline_input_hash",
    "scenario_input_hash",
    "warnings",
)


def scenario_summary_table(comparisons: Sequence[ScenarioComparison]) -> Table:
    rows = tuple(
        (
            c.scenario_id,
            c.scenario_name,
            c.baseline_run_id,
            c.scenario_run_id,
            c.status.value,
            c.verification_passed,
            c.objective_delta_usd,
            c.unfilled_demand_delta_shares,
            c.config_hash,
            c.baseline_input_hash,
            c.scenario_input_hash,
            _joined(c.warnings),
        )
        for c in comparisons
    )
    return Table(name="scenario_summary", columns=_SCENARIO_SUMMARY_COLUMNS, rows=rows)


_SCENARIO_ALLOCATION_COLUMNS = (
    "scenario_id",
    "route_id",
    "baseline_quantity_shares",
    "scenario_quantity_shares",
    "delta_shares",
    "reason_codes",
    "estimated_revenue_delta_usd",
)


def scenario_allocations_table(comparisons: Sequence[ScenarioComparison]) -> Table:
    rows = tuple(
        (
            c.scenario_id,
            a.route_id,
            a.baseline_quantity_shares,
            a.scenario_quantity_shares,
            a.delta_shares,
            _joined_enums(a.reason_codes),
            a.estimated_revenue_delta_usd,
        )
        for c in comparisons
        for a in c.allocations
    )
    return Table(name="scenario_allocations", columns=_SCENARIO_ALLOCATION_COLUMNS, rows=rows)


_SCENARIO_BALANCE_COLUMNS = (
    "scenario_id",
    "inventory_id",
    "baseline_total_lendable_shares",
    "scenario_total_lendable_shares",
    "baseline_available_shares",
    "scenario_available_shares",
    "baseline_utilization",
    "scenario_utilization",
)


def scenario_balances_table(comparisons: Sequence[ScenarioComparison]) -> Table:
    rows = tuple(
        (
            c.scenario_id,
            b.inventory_id,
            b.baseline_total_lendable_shares,
            b.scenario_total_lendable_shares,
            b.baseline_available_shares,
            b.scenario_available_shares,
            b.baseline_utilization,
            b.scenario_utilization,
        )
        for c in comparisons
        for b in c.balances
    )
    return Table(name="scenario_balances", columns=_SCENARIO_BALANCE_COLUMNS, rows=rows)


def scenario_economics_table(comparisons: Sequence[ScenarioComparison]) -> Table:
    """``economics_component_deltas`` is a mapping whose iteration order is not part of any
    upstream contract, so keys are sorted for byte-stable output (REQ-009)."""
    rows = tuple(
        (c.scenario_id, name, c.economics_component_deltas[name])
        for c in comparisons
        for name in sorted(c.economics_component_deltas)
    )
    return Table(
        name="scenario_economics",
        columns=("scenario_id", "component_name", "delta_usd"),
        rows=rows,
    )


def scenario_tables(comparisons: Sequence[ScenarioComparison]) -> tuple[Table, ...]:
    """Every table for a set of comparisons, in the documented order. Each table carries
    ``scenario_id`` so a multi-scenario run's rows concatenate cleanly (REQ-003/REQ-004)."""
    return (
        scenario_summary_table(comparisons),
        scenario_allocations_table(comparisons),
        scenario_balances_table(comparisons),
        scenario_economics_table(comparisons),
    )


# --------------------------------------------------------------------------------------
# StressTestReport
# --------------------------------------------------------------------------------------

_STRESS_SUMMARY_COLUMNS = (
    "scenario_count",
    "feasible_count",
    "infeasible_count",
    "verification_failed_count",
    "worst_case_scenario_id",
    "worst_case_objective_delta_usd",
)


def stress_summary_table(report: StressTestReport) -> Table:
    row: tuple[Cell, ...] = (
        report.scenario_count,
        report.feasible_count,
        report.infeasible_count,
        report.verification_failed_count,
        report.worst_case_scenario_id,
        report.worst_case_objective_delta_usd,
    )
    return Table(name="stress_summary", columns=_STRESS_SUMMARY_COLUMNS, rows=(row,))


_STRESS_OUTCOME_COLUMNS = (
    "scenario_id",
    "scenario_name",
    "status",
    "verification_passed",
    "objective_delta_usd",
)


def stress_outcomes_table(report: StressTestReport) -> Table:
    rows = tuple(
        (
            o.scenario_id,
            o.scenario_name,
            o.status.value,
            o.verification_passed,
            o.objective_delta_usd,
        )
        for o in report.outcomes
    )
    return Table(name="stress_outcomes", columns=_STRESS_OUTCOME_COLUMNS, rows=rows)


def stress_tables(report: StressTestReport) -> tuple[Table, ...]:
    return (stress_summary_table(report), stress_outcomes_table(report))


__all__ = [
    "Cell",
    "RunSummaryLayout",
    "Table",
    "allocation_evidence_table",
    "allocations_table",
    "balances_table",
    "constraints_table",
    "demand_table",
    "economics_table",
    "result_tables",
    "run_summary_long_table",
    "run_summary_table",
    "scenario_allocations_table",
    "scenario_balances_table",
    "scenario_economics_table",
    "scenario_summary_table",
    "scenario_tables",
    "stress_outcomes_table",
    "stress_summary_table",
    "stress_tables",
]
