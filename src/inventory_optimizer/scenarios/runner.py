"""Scenario and stress-test execution (T13-T14; Section 13.3 steps 8-9; SCN-003).

``run_scenario`` re-validates and re-solves a single scenario against an already-computed
baseline result; ``run_scenarios`` is a batch of the same call (batch/isolated equivalence by
construction -- both call the identical function, so there is no separate "batch path" that could
drift from the isolated one); ``run_stress_test`` aggregates a batch into one worst-case summary
(the additive, non-normative "basic stress testing" capability -- see spec.md).
"""

from __future__ import annotations

from collections.abc import Sequence

from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.results import OptimizationResult
from inventory_optimizer.domain.scenario_results import (
    ScenarioComparison,
    StressScenarioOutcome,
    StressTestReport,
)
from inventory_optimizer.domain.scenarios import Scenario
from inventory_optimizer.facade import InventoryOptimizer
from inventory_optimizer.scenarios.apply import apply_scenario
from inventory_optimizer.scenarios.compare import build_scenario_comparison
from inventory_optimizer.validation import raise_if_invalid


def run_scenario(
    baseline_request: OptimizationRequest,
    baseline_result: OptimizationResult,
    scenario: Scenario,
    optimizer: InventoryOptimizer,
) -> ScenarioComparison:
    scenario_request, apply_warnings = apply_scenario(baseline_request, scenario)
    raise_if_invalid(
        scenario_request, max_staleness_hours=optimizer.config.validation.max_staleness_hours
    )
    scenario_result = optimizer.optimize(scenario_request)
    return build_scenario_comparison(
        scenario=scenario,
        baseline_request=baseline_request,
        baseline_result=baseline_result,
        scenario_request=scenario_request,
        scenario_result=scenario_result,
        config=optimizer.config,
        apply_warnings=apply_warnings,
    )


def run_scenarios(
    baseline_request: OptimizationRequest,
    baseline_result: OptimizationResult,
    scenarios: Sequence[Scenario],
    optimizer: InventoryOptimizer,
) -> tuple[ScenarioComparison, ...]:
    return tuple(
        run_scenario(baseline_request, baseline_result, scenario, optimizer)
        for scenario in scenarios
    )


def run_stress_test(
    baseline_request: OptimizationRequest,
    baseline_result: OptimizationResult,
    scenarios: Sequence[Scenario],
    optimizer: InventoryOptimizer,
) -> StressTestReport:
    comparisons = run_scenarios(baseline_request, baseline_result, scenarios, optimizer)

    outcomes: list[StressScenarioOutcome] = []
    feasible_count = 0
    infeasible_count = 0
    verification_failed_count = 0
    worst_case: StressScenarioOutcome | None = None

    for comparison in comparisons:
        is_feasible = comparison.status.value in ("optimal", "feasible_limit")
        if is_feasible:
            feasible_count += 1
        else:
            infeasible_count += 1
        if not comparison.verification_passed:
            verification_failed_count += 1

        objective_delta = comparison.objective_delta_usd if is_feasible else None
        outcome = StressScenarioOutcome(
            scenario_id=comparison.scenario_id,
            scenario_name=comparison.scenario_name,
            status=comparison.status,
            verification_passed=comparison.verification_passed,
            objective_delta_usd=objective_delta,
        )
        outcomes.append(outcome)

        if objective_delta is not None and (
            worst_case is None
            or worst_case.objective_delta_usd is None
            or objective_delta < worst_case.objective_delta_usd
        ):
            worst_case = outcome

    return StressTestReport(
        scenario_count=len(comparisons),
        feasible_count=feasible_count,
        infeasible_count=infeasible_count,
        verification_failed_count=verification_failed_count,
        worst_case_scenario_id=worst_case.scenario_id if worst_case else None,
        worst_case_objective_delta_usd=worst_case.objective_delta_usd if worst_case else None,
        outcomes=tuple(outcomes),
    )
