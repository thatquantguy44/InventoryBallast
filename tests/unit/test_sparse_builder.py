"""``SparseBuilder`` / ``CompiledProblem`` unit behavior (Section 16.1).

The E1 golden-shape check lives in ``tests/golden/test_e1_scarce_name_allocation.py``.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from inventory_optimizer.domain.enums import Formulation, ObjectiveSense
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.sparse_builder import SparseBuilder
from inventory_optimizer.formulation.variables import build_variable_index


def test_compiled_problem_is_frozen() -> None:
    variable_index = build_variable_index([("q", ["RT-A"])])
    builder = SparseBuilder(variable_index)
    problem = builder.build(formulation=Formulation.LP, objective_sense=ObjectiveSense.MAXIMIZE)

    with pytest.raises(dataclasses.FrozenInstanceError):
        problem.formulation = Formulation.MIP  # type: ignore[misc]


def test_objective_coefficients_accumulate_additively() -> None:
    variable_index = build_variable_index([("q", ["RT-A"])])
    builder = SparseBuilder(variable_index)
    key = VariableKey("q", "RT-A")

    builder.add_objective_coefficient(key, 1.5)
    builder.add_objective_coefficient(key, 2.5)
    problem = builder.build(formulation=Formulation.LP, objective_sense=ObjectiveSense.MAXIMIZE)

    assert problem.linear_objective[0] == pytest.approx(4.0)


def test_duplicate_row_coefficients_sum_on_build() -> None:
    variable_index = build_variable_index([("q", ["RT-A"])])
    builder = SparseBuilder(variable_index)
    key = VariableKey("q", "RT-A")
    row = builder.add_row("some_row", "SCOPE-1", lower=0.0, upper=10.0)

    builder.add_row_coefficient(row, key, 1.0)
    builder.add_row_coefficient(row, key, 1.0)
    problem = builder.build(formulation=Formulation.LP, objective_sense=ObjectiveSense.MAXIMIZE)

    assert problem.constraint_matrix[0, 0] == pytest.approx(2.0)


def test_add_row_rejects_inverted_bounds() -> None:
    variable_index = build_variable_index([("q", ["RT-A"])])
    builder = SparseBuilder(variable_index)
    with pytest.raises(ValueError):
        builder.add_row("bad_row", "SCOPE-1", lower=10.0, upper=0.0)


def test_set_variable_bounds_rejects_inverted_bounds() -> None:
    variable_index = build_variable_index([("q", ["RT-A"])])
    builder = SparseBuilder(variable_index)
    with pytest.raises(ValueError):
        builder.set_variable_bounds(VariableKey("q", "RT-A"), lower=10.0, upper=0.0)


def test_unknown_variable_key_raises_keyerror() -> None:
    variable_index = build_variable_index([("q", ["RT-A"])])
    builder = SparseBuilder(variable_index)
    with pytest.raises(KeyError):
        builder.add_objective_coefficient(VariableKey("q", "RT-NOWHERE"), 1.0)


def test_default_bounds_match_section_11_3_convention() -> None:
    # "q_j >= 0" etc. with no stated upper bound: default lower=0, upper=+inf.
    variable_index = build_variable_index([("a", ["INV-1"])])
    builder = SparseBuilder(variable_index)
    problem = builder.build(formulation=Formulation.LP, objective_sense=ObjectiveSense.MAXIMIZE)

    assert problem.variable_lower[0] == 0.0
    assert problem.variable_upper[0] == math.inf
