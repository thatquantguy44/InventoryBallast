"""Objective attribution (T11; Section 18.2; VER-002, LP-007).

Enumerates every objective component recorded on ``CompiledProblem.manifest`` (the exact set that
ran during ``formulation.lp.compile_lp``, not a hardcoded list), calls each one's ``attribute()``,
and reconciles the sum against the solver's own claimed objective within the same tolerance T10's
independent verifier uses. A mismatch is never rounded away -- ``AttributionMismatchError`` is
raised so a drifting component or a lying solver result cannot reach a desk user labeled
"verified" (constitution P4; Locked Design Decision #8: "no silent repair").
"""

from __future__ import annotations

from inventory_optimizer.components.registry import ComponentKind
from inventory_optimizer.exceptions import AttributionMismatchError
from inventory_optimizer.reporting.types import ObjectiveAttribution, VerifiedSolution
from inventory_optimizer.validation.solution_verifier import DEFAULT_TOLERANCE


def attribute_objective(
    solution: VerifiedSolution, *, tolerance: float = DEFAULT_TOLERANCE
) -> tuple[ObjectiveAttribution, ...]:
    """Every registered objective component's independently-recomputed value, reconciled to
    ``solution.result.objective_value_unscaled``. Returns an empty tuple when there is no primal
    to attribute against (mirrors ``VerificationReport.has_primal``)."""
    if not solution.verification.has_primal:
        return ()

    attributions = tuple(
        registration.component_class().attribute(solution)
        for registration in solution.problem.manifest
        if registration.kind is ComponentKind.OBJECTIVE
    )

    attributed_sum = sum(attribution.unscaled_value_usd for attribution in attributions)
    claimed_objective = solution.result.objective_value_unscaled
    if claimed_objective is None or abs(attributed_sum - claimed_objective) > tolerance:
        raise AttributionMismatchError(
            attributed_sum=attributed_sum,
            claimed_objective=claimed_objective if claimed_objective is not None else float("nan"),
            tolerance=tolerance,
        )

    return attributions
