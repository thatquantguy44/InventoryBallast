"""EXAMPLES.md E1 -- Scarce-Name Allocation.

Reconstructs E1's compiled model by hand through the T07 formulation/sparse-builder layer and
checks the compiled shape matches the spec's worked example exactly. E1 is only *solved* once the
HiGHS backend and LP compiler land (T08-T09); until then this is the strongest available evidence
that the formulation infrastructure can represent the example faithfully.

    maximize (10 / 360) * (0.02 * q_A + 0.01 * q_B)

    subject to
        q_A + q_B + a = 100
        q_A + q_B <= 90
        0 <= q_A <= 80
        0 <= q_B <= 80
        a >= 0
"""

from __future__ import annotations

import math

import numpy as np

from inventory_optimizer.domain.enums import Formulation, ObjectiveSense
from inventory_optimizer.formulation.compiled import CompiledProblem, ScalingMetadata
from inventory_optimizer.formulation.indexes import RowKey, VariableKey
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


def test_e1_compiled_shape_matches_examples_md() -> None:
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
