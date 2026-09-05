"""Scenario comparison and stress-test report contracts (T13-T14; Section 13.4 of ``01_SPEC.md``,
scoped to what today's ``OptimizationResult`` (T11) actually computes -- see
``specs/0004-scenario-engine/spec.md``'s Non-Goals for the agency/prime/collateral/schedule fields
this does not attempt).

Same "domain imports nothing from formulation/validation/reporting" discipline
``domain/results.py`` (T11) established.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from inventory_optimizer.domain.enums import ReasonCode, SolverStatus


class RouteAllocationDelta(BaseModel):
    """One route's Section 13.4 "allocation delta by route" entry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    route_id: str
    baseline_quantity_shares: float
    scenario_quantity_shares: float
    delta_shares: float
    reason_codes: tuple[ReasonCode, ...] = ()
    estimated_revenue_delta_usd: float | None = None


class InventoryBalanceDelta(BaseModel):
    """One inventory record's Section 13.4 "post total lendable, on-loan, available, and
    utilization delta" entry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inventory_id: str
    baseline_total_lendable_shares: float
    scenario_total_lendable_shares: float
    baseline_available_shares: float
    scenario_available_shares: float
    baseline_utilization: float
    scenario_utilization: float


class ScenarioComparison(BaseModel):
    """Frozen boundary contract. Section 13.4's comparison output, scoped to fields computable
    from two already-built ``OptimizationResult``s plus the two requests -- see spec.md's
    Non-Goals for what this deliberately omits (agency/prime, collateral, schedule deltas)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: str
    scenario_name: str
    baseline_run_id: str
    scenario_run_id: str
    status: SolverStatus
    verification_passed: bool
    objective_delta_usd: float
    economics_component_deltas: Mapping[str, float]
    balances: tuple[InventoryBalanceDelta, ...]
    allocations: tuple[RouteAllocationDelta, ...]
    unfilled_demand_delta_shares: float
    warnings: tuple[str, ...] = ()
    config_hash: str
    baseline_input_hash: str
    scenario_input_hash: str


class StressScenarioOutcome(BaseModel):
    """One scenario's one-line verdict within a stress-test batch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: str
    scenario_name: str
    status: SolverStatus
    verification_passed: bool
    objective_delta_usd: float | None


class StressTestReport(BaseModel):
    """Frozen boundary contract. The additive, non-normative "basic stress testing" capability --
    see spec.md's Problem & Context."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_count: int
    feasible_count: int
    infeasible_count: int
    verification_failed_count: int
    worst_case_scenario_id: str | None
    worst_case_objective_delta_usd: float | None
    outcomes: tuple[StressScenarioOutcome, ...]
