"""Shared QP sign/PSD-validation helpers (T18; Section 14.2), used by ``formulation.qp::
compile_qp`` (compile-time PSD validation), ``solvers.highs`` (solve-time Hessian construction),
and ``validation.solution_verifier`` (verify-time objective reconstruction) so the maximize/
minimize sign convention and the positive-semidefinite check live in exactly one place, not three.

Convention: ``CompiledProblem.quadratic_objective`` (``Q``) is always validated positive
semidefinite (Section 14.2's literal requirement -- ``validate_psd`` below) and represents penalty
*intensity*, independent of ``objective_sense``. Its contribution to the declared sense's
optimized value is ``-0.5 * x^T Q x`` when maximizing (a concave penalty that discourages
deviation -- this engine's objective is always revenue, maximized) or ``+0.5 * x^T Q x`` when
minimizing (the equivalent convex cost, for a possible future minimize-sense formulation).
``signed_hessian``/``signed_quadratic_term`` apply this once so ``solvers.highs`` and
``validation.solution_verifier`` cannot drift out of sync with each other.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from inventory_optimizer.domain.enums import ObjectiveSense
from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.compiled import SparseMatrix

DEFAULT_PSD_TOLERANCE = 1e-8
_DENSE_EIGENVALUE_THRESHOLD = 64


def signed_hessian(matrix: SparseMatrix, sense: ObjectiveSense) -> SparseMatrix:
    return -matrix if sense is ObjectiveSense.MAXIMIZE else matrix


def signed_quadratic_term(
    matrix: SparseMatrix, primal: NDArray[np.float64], sense: ObjectiveSense
) -> float:
    raw = float(primal @ (matrix @ primal))
    return 0.5 * (-raw if sense is ObjectiveSense.MAXIMIZE else raw)


def _smallest_eigenvalue(matrix: SparseMatrix) -> float:
    if matrix.shape[0] <= _DENSE_EIGENVALUE_THRESHOLD:
        return float(np.linalg.eigvalsh(matrix.toarray()).min())
    from scipy.sparse.linalg import eigsh  # local: only needed at Core-desk-plus scale

    values = eigsh(matrix.tocsr().astype(np.float64), k=1, which="SA", return_eigenvectors=False)
    return float(values[0])


def validate_psd(
    matrix: SparseMatrix, *, tolerance: float = DEFAULT_PSD_TOLERANCE
) -> tuple[ValidationIssue, ...]:
    """Section 14.2: "QP matrices must be symmetric and positive semidefinite within tolerance."
    Symmetry is guaranteed by construction (``SparseBuilder.add_quadratic_objective_coefficient``
    always contributes both ``Q[i,j]`` and ``Q[j,i]``); this checks the remaining PSD requirement
    against the fully assembled matrix, not any one component's contribution in isolation, so a
    future second QP objective term whose *sum* with this one is not PSD still gets caught."""
    smallest = _smallest_eigenvalue(matrix)
    if smallest < -tolerance:
        return (
            ValidationIssue(
                code="QP_NOT_POSITIVE_SEMIDEFINITE",
                message=(
                    f"assembled quadratic objective matrix is not positive semidefinite within "
                    f"tolerance {tolerance!r} (smallest eigenvalue {smallest!r}); Section 14.2 "
                    "requires every QP matrix to be PSD"
                ),
                location="quadratic_objective",
            ),
        )
    return ()
