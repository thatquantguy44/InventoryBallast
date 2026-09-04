"""Coordinate-form accumulation, converted once to CSR (Section 20.1: "build matrices in
coordinate form and convert once to the backend-preferred sparse format"; Section 16.1: "no
component may assemble a dense matrix proportional to routes x constraints").

Only the constraint matrix is sparse-accumulated. The objective, bound, and row-limit vectors are
dense NumPy arrays sized by variable/row count (not routes x constraints), which Section 16.1's
own ``CompiledProblem`` sketch already types as plain ``NDArray[np.float64]``.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import coo_matrix

from inventory_optimizer.domain.enums import Formulation, ObjectiveSense
from inventory_optimizer.formulation.compiled import (
    CompiledProblem,
    ComponentManifest,
    ScalingMetadata,
    SparseMatrix,
)
from inventory_optimizer.formulation.indexes import VariableIndex, VariableKey
from inventory_optimizer.formulation.rows import RowIndexBuilder


class SparseBuilder:
    """Accumulates one ``CompiledProblem`` from a fixed ``VariableIndex`` plus incrementally
    registered rows. Variables default to the Section 11.3 convention (lower bound zero, no upper
    bound) until a caller narrows them with ``set_variable_bounds``."""

    def __init__(self, variable_index: VariableIndex) -> None:
        self._variable_index = variable_index
        self._rows = RowIndexBuilder()
        self._row_lower: list[float] = []
        self._row_upper: list[float] = []
        self._coo_rows: list[int] = []
        self._coo_cols: list[int] = []
        self._coo_data: list[float] = []
        n = len(variable_index)
        self._linear_objective: NDArray[np.float64] = np.zeros(n, dtype=np.float64)
        self._variable_lower: NDArray[np.float64] = np.zeros(n, dtype=np.float64)
        self._variable_upper: NDArray[np.float64] = np.full(n, np.inf, dtype=np.float64)

    def add_row(self, kind: str, scope_id: str, *, lower: float, upper: float) -> int:
        if lower > upper:
            raise ValueError(f"row lower bound {lower!r} exceeds upper bound {upper!r}")
        position = self._rows.add(kind, scope_id)
        self._row_lower.append(lower)
        self._row_upper.append(upper)
        return position

    def add_row_coefficient(
        self, row_position: int, variable_key: VariableKey, value: float
    ) -> None:
        self._coo_rows.append(row_position)
        self._coo_cols.append(self._variable_index.position(variable_key))
        self._coo_data.append(value)

    def add_objective_coefficient(self, variable_key: VariableKey, value: float) -> None:
        """Additive: multiple objective components (Section 15.2) may each contribute to the same
        variable's coefficient."""
        self._linear_objective[self._variable_index.position(variable_key)] += value

    def set_variable_bounds(self, variable_key: VariableKey, *, lower: float, upper: float) -> None:
        if lower > upper:
            raise ValueError(f"variable lower bound {lower!r} exceeds upper bound {upper!r}")
        position = self._variable_index.position(variable_key)
        self._variable_lower[position] = lower
        self._variable_upper[position] = upper

    def build(
        self,
        *,
        formulation: Formulation,
        objective_sense: ObjectiveSense,
        quadratic_objective: SparseMatrix | None = None,
        integrality: NDArray[np.int8] | None = None,
        scaling: ScalingMetadata | None = None,
        manifest: ComponentManifest = (),
    ) -> CompiledProblem:
        row_index = self._rows.build()
        n_vars = len(self._variable_index)
        n_rows = len(row_index)
        constraint_matrix: SparseMatrix = coo_matrix(
            (self._coo_data, (self._coo_rows, self._coo_cols)),
            shape=(n_rows, n_vars),
            dtype=np.float64,
        ).tocsr()

        return CompiledProblem(
            formulation=formulation,
            objective_sense=objective_sense,
            linear_objective=self._linear_objective,
            quadratic_objective=quadratic_objective,
            constraint_matrix=constraint_matrix,
            row_lower=np.array(self._row_lower, dtype=np.float64),
            row_upper=np.array(self._row_upper, dtype=np.float64),
            variable_lower=self._variable_lower,
            variable_upper=self._variable_upper,
            integrality=(
                integrality if integrality is not None else np.zeros(n_vars, dtype=np.int8)
            ),
            variable_index=self._variable_index,
            row_index=row_index,
            scaling=scaling if scaling is not None else ScalingMetadata(),
            manifest=manifest,
        )
