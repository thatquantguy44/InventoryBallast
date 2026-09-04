"""HiGHS adapter (T09; Section 16.4): status normalization, MIP-dual suppression, and
registration. E1's actual solved value lives in ``tests/golden/``.
"""

from __future__ import annotations

import dataclasses
import math

import highspy
import numpy as np
import pytest

from inventory_optimizer.components.registry import ComponentKind, default_registry
from inventory_optimizer.domain.enums import Capability, Formulation, ObjectiveSense, SolverStatus
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder
from inventory_optimizer.formulation.variables import build_variable_index
from inventory_optimizer.ports.solver import SolverOptions
from inventory_optimizer.solvers.highs import HighsBackend, _normalize_status


def _make_info(primal_solution_status: int) -> highspy.HighsInfo:
    info = highspy.HighsInfo()
    info.primal_solution_status = primal_solution_status
    return info


@pytest.mark.parametrize(
    ("model_status", "expected"),
    [
        (highspy.HighsModelStatus.kOptimal, SolverStatus.OPTIMAL),
        (highspy.HighsModelStatus.kInfeasible, SolverStatus.INFEASIBLE),
        (highspy.HighsModelStatus.kUnbounded, SolverStatus.UNBOUNDED),
        (highspy.HighsModelStatus.kUnboundedOrInfeasible, SolverStatus.INFEASIBLE_OR_UNBOUNDED),
        (highspy.HighsModelStatus.kModelEmpty, SolverStatus.INVALID_MODEL),
        (highspy.HighsModelStatus.kModelError, SolverStatus.INVALID_MODEL),
        (highspy.HighsModelStatus.kInterrupt, SolverStatus.INTERRUPTED),
        (highspy.HighsModelStatus.kSolveError, SolverStatus.SOLVER_ERROR),
        (highspy.HighsModelStatus.kMemoryLimit, SolverStatus.SOLVER_ERROR),
    ],
)
def test_normalize_status_direct_mappings(model_status, expected) -> None:
    info = _make_info(highspy.kSolutionStatusNone)
    assert _normalize_status(model_status, info) is expected


def test_time_limit_with_feasible_incumbent_is_feasible_limit() -> None:
    info = _make_info(highspy.kSolutionStatusFeasible)
    status = _normalize_status(highspy.HighsModelStatus.kTimeLimit, info)
    assert status is SolverStatus.FEASIBLE_LIMIT


def test_time_limit_without_incumbent_is_never_feasible_limit() -> None:
    # Section 16.3: FEASIBLE_LIMIT requires a verified incumbent -- it must never be implied when
    # none exists.
    info = _make_info(highspy.kSolutionStatusNone)
    status = _normalize_status(highspy.HighsModelStatus.kTimeLimit, info)
    assert status is not SolverStatus.FEASIBLE_LIMIT
    assert status is not SolverStatus.OPTIMAL


def _tiny_problem(*, objective_coefficient: float, rows: list[tuple[float, float]] | None = None):
    variable_index = build_variable_index([("x", ["V1"])])
    builder = SparseBuilder(variable_index)
    key = VariableKey("x", "V1")
    for index, (lower, upper) in enumerate(rows or []):
        row = builder.add_row("r", str(index), lower=lower, upper=upper)
        builder.add_row_coefficient(row, key, 1.0)
    builder.add_objective_coefficient(key, objective_coefficient)
    return builder.build(formulation=Formulation.LP, objective_sense=ObjectiveSense.MAXIMIZE)


def test_solve_reports_infeasible() -> None:
    # x <= 1 and x >= 5 with 0 <= x <= 10 cannot both hold.
    problem = _tiny_problem(objective_coefficient=1.0, rows=[(-math.inf, 1.0), (5.0, math.inf)])
    result = HighsBackend().solve(problem, SolverOptions())
    assert result.status is SolverStatus.INFEASIBLE
    assert result.primal is None


def test_solve_reports_unbounded() -> None:
    # maximize x, x >= 0, no upper bound, no constraining row.
    problem = _tiny_problem(objective_coefficient=1.0, rows=[])
    result = HighsBackend().solve(problem, SolverOptions())
    assert result.status is SolverStatus.UNBOUNDED


def test_solve_result_carries_no_highs_objects(default_config, e1_request) -> None:
    from inventory_optimizer.formulation.lp import compile_lp

    problem = compile_lp(e1_request, default_config)
    result = HighsBackend().solve(problem, SolverOptions())

    assert isinstance(result.primal, np.ndarray)
    assert "highspy" not in type(result.primal).__module__
    assert isinstance(result.native_status, str)
    assert isinstance(result.termination_reason, str)


def test_mip_duals_are_suppressed(default_config, e1_request) -> None:
    # Section 18.4: "Do not report LP duals as valid MIP shadow prices." Force one column integer
    # and confirm duals/reduced costs come back None even though HiGHS still reports them
    # internally for the LP relaxation.
    from inventory_optimizer.formulation.lp import compile_lp

    problem = compile_lp(e1_request, default_config)
    mip_integrality = np.zeros_like(problem.integrality)
    mip_integrality[0] = 1
    mip_problem = dataclasses.replace(problem, integrality=mip_integrality)
    result = HighsBackend().solve(mip_problem, SolverOptions())
    assert result.dual is None
    assert result.reduced_costs is None


def test_backend_is_registered_with_lp_and_mip_capabilities() -> None:
    registration = default_registry.get(ComponentKind.SOLVER_BACKEND, "highs", "1")
    assert registration.component_class is HighsBackend
    assert registration.metadata["capabilities"] == frozenset({Capability.LP, Capability.MIP})
    assert HighsBackend().capabilities == frozenset({Capability.LP, Capability.MIP})


def test_repeated_compile_and_solve_is_deterministic(default_config, e1_request) -> None:
    """Section 16.5: sorted IDs, deterministic component order, and a fixed seed/thread count
    (Section 20.1's incremental-reuse concerns aside) should make repeated compiles/solves of the
    same request agree exactly -- not just within tolerance."""
    from inventory_optimizer.formulation.lp import compile_lp

    options = SolverOptions(seed=1, threads=1)
    results = []
    for _ in range(3):
        problem = compile_lp(e1_request, default_config)
        results.append(HighsBackend().solve(problem, options))

    first = results[0]
    for other in results[1:]:
        assert other.status is first.status
        assert other.objective_value_unscaled == first.objective_value_unscaled
        np.testing.assert_array_equal(other.primal, first.primal)
        assert other.native_status == first.native_status
