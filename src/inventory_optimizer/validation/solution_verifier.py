"""Independent solution verifier (T10, T18; Section 18.1 "Verification", requirement VER-001).

Recomputes primal feasibility, integrality, and the objective directly from a ``CompiledProblem``
and a ``SolverResult`` -- never trusting the solver's own claim (Locked Design Decision #8: "no
silent repair"; Section 27's risk: "solver status misinterpreted -> unsafe recommendation").

Deliberately independent of ``result.status``: a ``FEASIBLE_LIMIT`` result with a primal that
satisfies every bound/row/integrality check and matches its claimed objective still passes here --
this only checks whether the returned primal *is* what it claims to be, not whether it is optimal.

The objective reconstruction includes ``problem.quadratic_objective`` (Section 14.2) via
``formulation.qp_support.signed_quadratic_term`` whenever a QP compile set it -- omitting it would
make every correct QP solve fail this check by exactly the magnitude of its quadratic term.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from inventory_optimizer.formulation.compiled import CompiledProblem
from inventory_optimizer.formulation.qp_support import signed_quadratic_term
from inventory_optimizer.ports.solver import SolverResult

DEFAULT_TOLERANCE = 1e-6


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Section 18.1's "Verification" section: max violations and the objective reconstruction
    delta. ``passed`` is true only when every check is within tolerance and a primal was actually
    present to check (Section 16.3: "results without a feasible primal vector do not produce
    allocation recommendations")."""

    has_primal: bool
    max_variable_bound_violation: float
    max_row_violation: float
    max_integrality_violation: float
    objective_reconstruction_delta: float
    passed: bool


def verify_solution(
    problem: CompiledProblem, result: SolverResult, *, tolerance: float = DEFAULT_TOLERANCE
) -> VerificationReport:
    if result.primal is None:
        return VerificationReport(
            has_primal=False,
            max_variable_bound_violation=math.inf,
            max_row_violation=math.inf,
            max_integrality_violation=math.inf,
            objective_reconstruction_delta=math.inf,
            passed=False,
        )

    primal = result.primal

    bound_violations = np.maximum(
        problem.variable_lower - primal, primal - problem.variable_upper
    )
    max_variable_bound_violation = max(float(np.max(bound_violations)), 0.0) if len(primal) else 0.0

    row_activity = problem.constraint_matrix @ primal
    row_violations = np.maximum(problem.row_lower - row_activity, row_activity - problem.row_upper)
    max_row_violation = max(float(np.max(row_violations)), 0.0) if len(row_violations) else 0.0

    integer_mask = problem.integrality != 0
    if np.any(integer_mask):
        integer_values = primal[integer_mask]
        max_integrality_violation = float(np.max(np.abs(integer_values - np.round(integer_values))))
    else:
        max_integrality_violation = 0.0

    reconstructed_objective = float(problem.linear_objective @ primal)
    if problem.quadratic_objective is not None:
        reconstructed_objective += signed_quadratic_term(
            problem.quadratic_objective, primal, problem.objective_sense
        )
    claimed_objective = result.objective_value_unscaled
    objective_reconstruction_delta = (
        abs(reconstructed_objective - claimed_objective)
        if claimed_objective is not None
        else math.inf
    )

    passed = (
        max_variable_bound_violation <= tolerance
        and max_row_violation <= tolerance
        and max_integrality_violation <= tolerance
        and objective_reconstruction_delta <= tolerance
    )

    return VerificationReport(
        has_primal=True,
        max_variable_bound_violation=max_variable_bound_violation,
        max_row_violation=max_row_violation,
        max_integrality_violation=max_integrality_violation,
        objective_reconstruction_delta=objective_reconstruction_delta,
        passed=passed,
    )
