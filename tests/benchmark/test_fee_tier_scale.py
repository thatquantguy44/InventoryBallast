"""specs/0009-discrete-fee-tier-pricing/spec.md RISK-001's "scaling tests": does compile+solve+
verify complete, correctly, within a generous ceiling once a request has enough tiered demand
groups that the `J*K` per-route-per-tier variable growth (`plan.md`'s Variables section) is
material -- ``J`` routes and ``K`` tiers per group add ``J*K`` continuous ``w`` variables plus
``K`` binary ``t`` variables, *per tiered group*. Not a tracked-baseline performance-regression
suite, matching `tests/benchmark/test_qp_scale.py`'s own precedent -- a moderate scale confirming
the fee-tier path (the three new row families, per-tier integrality, the delta objective term)
stays fast and correct well beyond a single hand-built fixture, not stress-testing the solver's
absolute scale ceiling.

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
from inventory_optimizer.formulation.mip import compile_mip
from inventory_optimizer.ports.solver import SolverOptions
from inventory_optimizer.solvers.highs import HighsBackend
from inventory_optimizer.validation.solution_verifier import verify_solution

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)

_N_GROUPS = 20
_ROUTES_PER_GROUP = 10
_TIERS_PER_GROUP = 10
_WALL_CLOCK_CEILING_SECONDS = 60.0


def _build_tiered_scale_request() -> OptimizationRequest:
    inventories: list[SecurityInventory] = []
    routes: list[LoanRoute] = []
    demand: list[DemandForecast] = []

    for i in range(_N_GROUPS):
        inventory_id = f"INV-{i}"
        total_lendable = float(_ROUTES_PER_GROUP * 100)
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
        demand.append(
            DemandForecast(
                demand_group_id=f"DG-{i}",
                security_id=f"SEC-{i}",
                borrower_id=f"BORROWER-{i}",
                as_of=_AS_OF,
                reference_quantity_shares=100.0 * _ROUTES_PER_GROUP,
                reference_fee_rate=0.02,
                elasticity=0.0,
                source_model="bench",
                source_version="bench-v1",
                candidate_fee_rates=tuple(
                    0.01 + 0.001 * tier_index for tier_index in range(_TIERS_PER_GROUP)
                ),
            )
        )
        for r in range(_ROUTES_PER_GROUP):
            routes.append(
                LoanRoute(
                    route_id=f"RT-{i}-{r}",
                    inventory_id=inventory_id,
                    security_id=f"SEC-{i}",
                    borrower_id=f"BORROWER-{i}",
                    demand_group_id=f"DG-{i}",
                    current_quantity_shares=0.0,
                    hard_minimum_quantity_shares=0.0,
                    maximum_quantity_shares=100.0,
                    fee_rate=0.02,
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
        request_id="REQ-FEE-TIER-SCALE-BENCH",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=tuple(inventories),
        routes=tuple(routes),
        demand=tuple(demand),
    )


@pytest.mark.slow
def test_fee_tier_compile_and_solve_completes_within_time_ceiling(default_config) -> None:
    """``_N_GROUPS`` tiered groups of ``_ROUTES_PER_GROUP`` routes and ``_TIERS_PER_GROUP``
    candidate fees each: ``_N_GROUPS * _ROUTES_PER_GROUP * _TIERS_PER_GROUP`` = 2,000 `w`
    variables plus ``_N_GROUPS * _TIERS_PER_GROUP`` = 200 binary `t` variables, on top of the
    existing `q`/`inc`/`dec`/`a` blocks."""
    start = time.perf_counter()
    request = _build_tiered_scale_request()
    problem = compile_mip(request, default_config)

    result = HighsBackend().solve(problem, SolverOptions())
    report = verify_solution(problem, result)
    elapsed = time.perf_counter() - start

    assert result.status is SolverStatus.OPTIMAL
    assert report.passed is True
    assert elapsed < _WALL_CLOCK_CEILING_SECONDS, (
        f"fee-tier scaling benchmark took {elapsed:.1f}s, exceeding the "
        f"{_WALL_CLOCK_CEILING_SECONDS}s generous ceiling -- investigate for a catastrophic "
        "regression (not a tight perf budget)."
    )
