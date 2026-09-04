"""``CompiledProblem`` (Section 16.1): the solver-neutral output of the formulation layer.

This is a pure data shape. Populating it -- deciding which constraint/objective components run
and in what order -- is the LP/MIP/QP compiler's job (T08/T15/T18), not this module's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

import numpy as np
import scipy.sparse
from numpy.typing import NDArray

from inventory_optimizer.components.registry import ComponentRegistration
from inventory_optimizer.domain.enums import Formulation, ObjectiveSense
from inventory_optimizer.formulation.indexes import RowIndex, VariableIndex

SparseMatrix: TypeAlias = scipy.sparse.csr_matrix
ComponentManifest: TypeAlias = tuple[ComponentRegistration, ...]


@dataclass(frozen=True, slots=True)
class ScalingMetadata:
    """Section 20.3: "store both scaled and original values in ScalingMetadata." No scaling is
    computed yet (``applied=False`` is the Phase-1 default); the fields exist so a later scaling
    pass (T08/T09) does not need a ``CompiledProblem`` shape change."""

    applied: bool = False
    quantity_scale: float = 1.0
    objective_scale_usd: float = 1.0


@dataclass(frozen=True, slots=True)
class CompiledProblem:
    formulation: Formulation
    objective_sense: ObjectiveSense
    linear_objective: NDArray[np.float64]
    quadratic_objective: SparseMatrix | None
    constraint_matrix: SparseMatrix
    row_lower: NDArray[np.float64]
    row_upper: NDArray[np.float64]
    variable_lower: NDArray[np.float64]
    variable_upper: NDArray[np.float64]
    integrality: NDArray[np.int8]
    variable_index: VariableIndex
    row_index: RowIndex
    scaling: ScalingMetadata
    manifest: ComponentManifest
