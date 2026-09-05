"""``formulation.qp_support`` unit tests (specs/0007-qp-allocation-stability/spec.md AC-006):
``validate_psd`` on both its dense (small-matrix) and sparse ``eigsh`` (large-matrix) code paths,
plus ``signed_hessian``/``signed_quadratic_term``'s maximize/minimize sign convention.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from inventory_optimizer.domain.enums import ObjectiveSense
from inventory_optimizer.formulation.qp_support import (
    _DENSE_EIGENVALUE_THRESHOLD,
    signed_hessian,
    signed_quadratic_term,
    validate_psd,
)


def test_validate_psd_accepts_psd_matrix() -> None:
    matrix = csr_matrix(np.diag([1.0, 2.0, 0.0]))
    assert validate_psd(matrix) == ()


def test_validate_psd_rejects_indefinite_matrix() -> None:
    """[[0, 2], [2, 0]] has eigenvalues +-2 -- clearly not PSD."""
    matrix = csr_matrix(np.array([[0.0, 2.0], [2.0, 0.0]]))

    issues = validate_psd(matrix)

    assert len(issues) == 1
    assert issues[0].code == "QP_NOT_POSITIVE_SEMIDEFINITE"
    assert issues[0].location == "quadratic_objective"


def test_validate_psd_sparse_path_rejects_indefinite_block() -> None:
    """A matrix larger than the dense threshold, mostly identity, with one bad 2x2 block --
    exercises the scipy.sparse.linalg.eigsh code path specifically."""
    dim = _DENSE_EIGENVALUE_THRESHOLD + 16
    dense = np.eye(dim)
    dense[10, 11] = 5.0
    dense[11, 10] = 5.0  # eigenvalues of that 2x2 block: 1 +- 5 -> -4, indefinite
    matrix = csr_matrix(dense)

    issues = validate_psd(matrix)

    assert len(issues) == 1
    assert issues[0].code == "QP_NOT_POSITIVE_SEMIDEFINITE"


def test_validate_psd_sparse_path_accepts_identity() -> None:
    dim = _DENSE_EIGENVALUE_THRESHOLD + 16
    matrix = csr_matrix(np.eye(dim))

    assert validate_psd(matrix) == ()


def test_signed_hessian_negates_for_maximize() -> None:
    matrix = csr_matrix(np.diag([1.0, 2.0]))

    maximized = signed_hessian(matrix, ObjectiveSense.MAXIMIZE)
    minimized = signed_hessian(matrix, ObjectiveSense.MINIMIZE)

    assert maximized.toarray().tolist() == [[-1.0, 0.0], [0.0, -2.0]]
    assert minimized.toarray().tolist() == [[1.0, 0.0], [0.0, 2.0]]


def test_signed_quadratic_term_matches_hand_formula() -> None:
    matrix = csr_matrix(np.diag([1.0]))
    primal = np.array([3.0])

    maximized = signed_quadratic_term(matrix, primal, ObjectiveSense.MAXIMIZE)
    minimized = signed_quadratic_term(matrix, primal, ObjectiveSense.MINIMIZE)

    assert maximized == pytest.approx(-0.5 * 1.0 * 9.0)
    assert minimized == pytest.approx(0.5 * 1.0 * 9.0)
