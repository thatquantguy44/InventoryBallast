"""Shadow-price tests (T11; Section 18.4).

AC-008 solves the real E1 fixture: its utilization-cap row is the one that actually binds (E1's
inventory balance is scarce, Section 20.2's benchmark note), so it must carry a nonzero, labeled,
traceable dual. AC-009 proves the MIP guard: whenever the backend reports no dual (as HiGHS already
guarantees for any solve with integer variables), no shadow price is ever fabricated.
"""

from __future__ import annotations

import dataclasses

from inventory_optimizer.formulation.indexes import RowKey
from inventory_optimizer.reporting.shadow_prices import build_shadow_prices
from inventory_optimizer.reporting.types import VerifiedSolution


def test_binding_row_duals_labeled_and_traceable(e1_solution: VerifiedSolution) -> None:
    """AC-008."""
    shadow_prices = {entry.row_key: entry for entry in build_shadow_prices(e1_solution)}

    binding_row = RowKey("utilization_max", "INV-1:UP-1")
    assert binding_row in shadow_prices
    entry = shadow_prices[binding_row]
    assert entry.dual_value != 0.0
    assert entry.objective_scale_usd == e1_solution.problem.scaling.objective_scale_usd
    assert entry.sign_convention


def test_mip_solve_has_no_shadow_prices(e1_solution: VerifiedSolution) -> None:
    """AC-009."""
    integer_result = dataclasses.replace(e1_solution.result, dual=None)
    integer_solution = dataclasses.replace(e1_solution, result=integer_result)

    assert build_shadow_prices(integer_solution) == ()
