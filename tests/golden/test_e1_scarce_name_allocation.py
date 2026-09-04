"""EXAMPLES.md E1 -- Scarce-Name Allocation.

    maximize (10 / 360) * (0.02 * q_A + 0.01 * q_B)

    subject to
        q_A + q_B + a = 100
        q_A + q_B <= 90
        0 <= q_A <= 80
        0 <= q_B <= 80
        a >= 0

Two checks:

1. A hand-built ``CompiledProblem`` through the raw T07 ``SparseBuilder`` (no request, no
   compiler) -- proves the formulation infrastructure alone can represent E1's exact shape.
2. The real ``formulation.lp.compile_lp()`` (T08) run on the ``e1_request`` fixture and solved
   with ``scipy.optimize.linprog`` -- proves the compiler produces E1's exact expected allocation
   end to end. This is *not* the T09 HiGHS adapter (Section 16.4 reserves ``highspy`` for that);
   it is scipy's own bundled HiGHS-based solver, used here only because ``highspy`` is not
   installed in this environment. The normalized-status/verifier machinery is T09/T10.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.optimize import linprog

from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.domain.enums import Formulation, ObjectiveSense
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.formulation.compiled import CompiledProblem, ScalingMetadata
from inventory_optimizer.formulation.indexes import RowKey, VariableKey
from inventory_optimizer.formulation.lp import compile_lp
from inventory_optimizer.formulation.sparse_builder import SparseBuilder
from inventory_optimizer.formulation.variables import build_variable_index


def build_e1_compiled_problem() -> CompiledProblem:
    variable_index = build_variable_index([("q", ["RT-A", "RT-B"]), ("a", ["INV-1"])])
    builder = SparseBuilder(variable_index)
    q_a, q_b, a = (
        VariableKey("q", "RT-A"),
        VariableKey("q", "RT-B"),
        VariableKey("a", "INV-1"),
    )

    balance_row = builder.add_row("inventory_balance", "INV-1", lower=100.0, upper=100.0)
    builder.add_row_coefficient(balance_row, q_a, 1.0)
    builder.add_row_coefficient(balance_row, q_b, 1.0)
    builder.add_row_coefficient(balance_row, a, 1.0)

    utilization_row = builder.add_row("utilization_cap", "INV-1", lower=-math.inf, upper=90.0)
    builder.add_row_coefficient(utilization_row, q_a, 1.0)
    builder.add_row_coefficient(utilization_row, q_b, 1.0)

    builder.set_variable_bounds(q_a, lower=0.0, upper=80.0)
    builder.set_variable_bounds(q_b, lower=0.0, upper=80.0)

    tau = 10.0 / 360.0
    builder.add_objective_coefficient(q_a, tau * 0.02)
    builder.add_objective_coefficient(q_b, tau * 0.01)

    return builder.build(formulation=Formulation.LP, objective_sense=ObjectiveSense.MAXIMIZE)


def test_e1_hand_built_compiled_shape_matches_examples_md() -> None:
    problem = build_e1_compiled_problem()

    assert problem.constraint_matrix.shape == (2, 3)
    np.testing.assert_array_equal(
        problem.constraint_matrix.toarray(), [[1.0, 1.0, 1.0], [1.0, 1.0, 0.0]]
    )
    np.testing.assert_array_equal(problem.row_lower, [100.0, -math.inf])
    np.testing.assert_array_equal(problem.row_upper, [100.0, 90.0])
    np.testing.assert_array_equal(problem.variable_lower, [0.0, 0.0, 0.0])
    np.testing.assert_array_equal(problem.variable_upper, [80.0, 80.0, math.inf])
    np.testing.assert_allclose(
        problem.linear_objective, [10.0 / 360.0 * 0.02, 10.0 / 360.0 * 0.01, 0.0]
    )
    np.testing.assert_array_equal(problem.integrality, [0, 0, 0])
    assert problem.formulation is Formulation.LP
    assert problem.objective_sense is ObjectiveSense.MAXIMIZE
    assert problem.quadratic_objective is None
    assert problem.scaling == ScalingMetadata()
    assert problem.manifest == ()

    assert problem.variable_index.position(VariableKey("q", "RT-A")) == 0
    assert problem.row_index.key(0) == RowKey("inventory_balance", "INV-1")
    assert problem.row_index.key(1) == RowKey("utilization_cap", "INV-1")


def _solve_with_scipy(problem: CompiledProblem) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
    """Interim solve for golden-value verification only; see module docstring."""
    dense = problem.constraint_matrix.toarray()
    a_ub: list[np.ndarray] = []
    b_ub: list[float] = []
    a_eq: list[np.ndarray] = []
    b_eq: list[float] = []
    for row, (lower, upper) in enumerate(
        zip(problem.row_lower, problem.row_upper, strict=True)
    ):
        if lower == upper:
            a_eq.append(dense[row])
            b_eq.append(lower)
            continue
        if upper != math.inf:
            a_ub.append(dense[row])
            b_ub.append(upper)
        if lower != -math.inf:
            a_ub.append(-dense[row])
            b_ub.append(-lower)

    result = linprog(
        c=-problem.linear_objective,
        A_ub=a_ub or None,
        b_ub=b_ub or None,
        A_eq=a_eq or None,
        b_eq=b_eq or None,
        bounds=list(zip(problem.variable_lower, problem.variable_upper, strict=True)),
        method="highs",
    )
    assert result.success, result.message
    return result.x


def test_e1_compiles_and_solves_to_expected_allocation(
    e1_request: OptimizationRequest, default_config: InventoryOptimizerConfig
) -> None:
    problem = compile_lp(e1_request, default_config)
    solution = _solve_with_scipy(problem)

    q_a = solution[problem.variable_index.position(VariableKey("q", "RT-A"))]
    q_b = solution[problem.variable_index.position(VariableKey("q", "RT-B"))]
    available = solution[problem.variable_index.position(VariableKey("a", "INV-1"))]
    objective = float(problem.linear_objective @ solution)

    assert q_a == pytest.approx(80.0)
    assert q_b == pytest.approx(10.0)
    assert available == pytest.approx(10.0)
    assert objective == pytest.approx(0.0472222222, rel=1e-6)
