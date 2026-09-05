"""LP shadow prices (T11; Section 18.4; VER-006's Constraints section).

Row duals are reported only for a continuous LP solve whose primal has already passed independent
verification -- the HiGHS backend (``solvers/highs.py``) already guarantees ``SolverResult.dual``
is ``None`` whenever integer variables were present, so this module's own guard is what keeps a MIP
result from ever being labeled with a (locally invalid) LP dual (Section 18.4: "do not report LP
duals as valid MIP shadow prices").
"""

from __future__ import annotations

from inventory_optimizer.reporting.types import ShadowPriceEntry, VerifiedSolution

SIGN_CONVENTION = (
    "objective is maximized; dual_value is the marginal increase in the unscaled USD objective "
    "per one-unit relaxation of this row's binding bound (negative if tightening would help)"
)


def build_shadow_prices(solution: VerifiedSolution) -> tuple[ShadowPriceEntry, ...]:
    result = solution.result
    if result.dual is None or not solution.verification.passed:
        return ()

    scale = solution.problem.scaling.objective_scale_usd
    return tuple(
        ShadowPriceEntry(
            row_key=row_key,
            dual_value=float(dual_value),
            objective_scale_usd=scale,
            sign_convention=SIGN_CONVENTION,
        )
        for row_key, dual_value in zip(
            solution.problem.row_index.keys, result.dual, strict=True
        )
    )
