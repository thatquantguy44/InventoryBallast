"""01_SPEC.md Section 20.2 -- Core desk benchmark shape, as a smoke test (specs/0005-test-hardening/
spec.md AC-013). Not a tracked-baseline performance-regression suite (no such infrastructure exists
here yet, per spec.md's Non-Goals) -- just "does compile+solve+verify complete, correctly, within a
generous ceiling" at roughly the Core desk row counts (5,000 inventory / 50,000 routes / ~25,000
demand groups; the owner/scenario axes of Section 20.2's table don't apply to the baseline family's
single-owner, single-solve shape -- see spec.md's Assumptions).

Marked ``slow`` (excluded from the default ``pytest tests/ -q`` run via ``addopts`` in
pyproject.toml); run explicitly with ``pytest tests/ -m slow -q``.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime

import pytest

from inventory_optimizer.domain.demand import DemandForecast
from inventory_optimizer.domain.enums import SolverStatus
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.formulation.lp import compile_lp
from inventory_optimizer.ports.solver import SolverOptions
from inventory_optimizer.solvers.highs import HighsBackend
from inventory_optimizer.validation.solution_verifier import verify_solution

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)

_N_INVENTORY = 5_000
_ROUTES_PER_INVENTORY = 10
_DEMAND_GROUPS_PER_INVENTORY = 5
_WALL_CLOCK_CEILING_SECONDS = 120.0


def _build_core_desk_request() -> OptimizationRequest:
    routes_per_group = _ROUTES_PER_INVENTORY // _DEMAND_GROUPS_PER_INVENTORY
    inventories: list[SecurityInventory] = []
    routes: list[LoanRoute] = []
    demand: list[DemandForecast] = []

    for i in range(_N_INVENTORY):
        inventory_id = f"INV-{i}"
        total_lendable = float(_ROUTES_PER_INVENTORY * 100)
        inventories.append(
            SecurityInventory(
                inventory_id=inventory_id,
                inventory_pool_id=f"POOL-{i}",
                security_id=f"SEC-{i}",
                as_of=_AS_OF,
                settlement_date=_EFFECTIVE_DATE,
                total_lendable_shares=total_lendable,
                on_loan_shares=0.0,
                reserved_shares=0.0,
                committed_out_shares=0.0,
                available_to_lend_shares=total_lendable,
                price_usd=10.0,
                currency="USD",
                eligible=True,
                source_version="bench-v1",
            )
        )
        for g in range(_DEMAND_GROUPS_PER_INVENTORY):
            demand.append(
                DemandForecast(
                    demand_group_id=f"DG-{i}-{g}",
                    security_id=f"SEC-{i}",
                    borrower_id=f"BORROWER-{i}-{g}",
                    as_of=_AS_OF,
                    reference_quantity_shares=100.0 * routes_per_group,
                    reference_fee_rate=0.01 + 0.001 * g,
                    elasticity=0.0,
                    source_model="bench",
                    source_version="bench-v1",
                )
            )
        for r in range(_ROUTES_PER_INVENTORY):
            group_index = r % _DEMAND_GROUPS_PER_INVENTORY
            routes.append(
                LoanRoute(
                    route_id=f"RT-{i}-{r}",
                    inventory_id=inventory_id,
                    security_id=f"SEC-{i}",
                    borrower_id=f"BORROWER-{i}-{group_index}",
                    demand_group_id=f"DG-{i}-{group_index}",
                    current_quantity_shares=0.0,
                    hard_minimum_quantity_shares=0.0,
                    maximum_quantity_shares=100.0,
                    fee_rate=0.01 + 0.001 * group_index,
                    revenue_share=1.0,
                    variable_cost_rate=0.0,
                    increase_cost_usd_per_share=0.0,
                    decrease_cost_usd_per_share=0.0,
                    recall_notice_days=0,
                    term_end_date=None,
                    eligible=True,
                    all_or_none=False,
                )
            )

    return OptimizationRequest(
        request_id="REQ-CORE-DESK-BENCH",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=tuple(inventories),
        routes=tuple(routes),
        demand=tuple(demand),
    )


@pytest.mark.slow
def test_core_desk_scale_compiles_and_solves_within_ceiling(default_config) -> None:
    start = time.perf_counter()
    request = _build_core_desk_request()
    problem = compile_lp(request, default_config)
    result = HighsBackend().solve(problem, SolverOptions())
    report = verify_solution(problem, result)
    elapsed = time.perf_counter() - start

    assert result.status is SolverStatus.OPTIMAL
    assert report.passed is True
    assert elapsed < _WALL_CLOCK_CEILING_SECONDS, (
        f"Core desk benchmark took {elapsed:.1f}s, exceeding the {_WALL_CLOCK_CEILING_SECONDS}s "
        "generous ceiling -- investigate for a catastrophic regression (not a tight perf budget)."
    )
