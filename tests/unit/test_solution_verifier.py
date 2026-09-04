"""Independent solution verifier (T10; VER-001): corrupted-solution tests.

Solves E1 for real, then deliberately corrupts one aspect of the result at a time and confirms
``verify_solution`` catches exactly that corruption. A verifier that always says "fine" is worse
than no verifier -- these tests exist to prove it isn't one.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from inventory_optimizer.domain.enums import SolverStatus
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.lp import compile_lp
from inventory_optimizer.ports.solver import SolverOptions
from inventory_optimizer.solvers.highs import HighsBackend
from inventory_optimizer.validation import DEFAULT_TOLERANCE, verify_solution


@pytest.fixture
def e1_solution(e1_request, default_config):
    problem = compile_lp(e1_request, default_config)
    result = HighsBackend().solve(problem, SolverOptions())
    assert result.status is SolverStatus.OPTIMAL
    return problem, result


def test_genuine_solution_passes_with_negligible_violations(e1_solution) -> None:
    problem, result = e1_solution
    report = verify_solution(problem, result)

    assert report.has_primal is True
    assert report.passed is True
    assert report.max_variable_bound_violation <= DEFAULT_TOLERANCE
    assert report.max_row_violation <= DEFAULT_TOLERANCE
    assert report.max_integrality_violation <= DEFAULT_TOLERANCE
    assert report.objective_reconstruction_delta <= DEFAULT_TOLERANCE


def test_missing_primal_never_passes(e1_solution) -> None:
    problem, result = e1_solution
    corrupted = dataclasses.replace(result, primal=None)

    report = verify_solution(problem, corrupted)

    assert report.has_primal is False
    assert report.passed is False


def test_variable_bound_violation_is_caught(e1_solution) -> None:
    problem, result = e1_solution
    position = problem.variable_index.position(VariableKey("q", "RT-A"))
    corrupted_primal = result.primal.copy()
    corrupted_primal[position] = problem.variable_upper[position] + 1.0  # pushed past its own max
    corrupted = dataclasses.replace(result, primal=corrupted_primal)

    report = verify_solution(problem, corrupted)

    assert report.passed is False
    assert report.max_variable_bound_violation == pytest.approx(1.0)


def test_row_violation_is_caught(e1_solution) -> None:
    problem, result = e1_solution
    # Increase q_A without touching a_i or q_B: breaks the inventory-balance equality.
    position = problem.variable_index.position(VariableKey("q", "RT-A"))
    corrupted_primal = result.primal.copy()
    corrupted_primal[position] += 5.0
    corrupted = dataclasses.replace(result, primal=corrupted_primal)

    report = verify_solution(problem, corrupted)

    assert report.passed is False
    assert report.max_row_violation == pytest.approx(5.0)


def test_integrality_violation_is_caught(e1_solution) -> None:
    problem, result = e1_solution
    mip_integrality = np.zeros_like(problem.integrality)
    position = problem.variable_index.position(VariableKey("q", "RT-B"))
    mip_integrality[position] = 1
    mip_problem = dataclasses.replace(problem, integrality=mip_integrality)

    corrupted_primal = result.primal.copy()
    corrupted_primal[position] += 0.5  # q_B was 10.0 (integral); now 10.5

    corrupted = dataclasses.replace(result, primal=corrupted_primal)
    report = verify_solution(mip_problem, corrupted)

    assert report.passed is False
    assert report.max_integrality_violation == pytest.approx(0.5)


def test_falsified_objective_is_caught(e1_solution) -> None:
    problem, result = e1_solution
    falsified_objective = result.objective_value_unscaled + 1.0
    corrupted = dataclasses.replace(result, objective_value_unscaled=falsified_objective)

    report = verify_solution(problem, corrupted)

    assert report.passed is False
    assert report.objective_reconstruction_delta == pytest.approx(1.0)


def test_missing_objective_never_passes(e1_solution) -> None:
    problem, result = e1_solution
    corrupted = dataclasses.replace(result, objective_value_unscaled=None)

    report = verify_solution(problem, corrupted)

    assert report.passed is False
    assert report.objective_reconstruction_delta == float("inf")


def test_feasible_limit_with_valid_primal_still_passes(e1_solution) -> None:
    # Verification checks whether the primal IS what it claims, independent of whether the solver
    # proved it optimal.
    problem, result = e1_solution
    limited = dataclasses.replace(result, status=SolverStatus.FEASIBLE_LIMIT)

    report = verify_solution(problem, limited)

    assert report.passed is True
