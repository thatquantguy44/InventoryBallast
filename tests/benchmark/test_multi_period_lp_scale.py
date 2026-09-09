"""specs/0010-multi-period-settlement/spec.md RISK-004's scaling test: does
``compile_multi_period_lp``/``solve_multi_period`` complete, correctly, within a generous ceiling
at a moderate scale, sizing the ``route count x period count`` growth RISK-004 flags -- the same
dimension `specs/0009-discrete-fee-tier-pricing/spec.md` RISK-001 flagged for its own tier
dimension, here potentially larger since it applies to every route across every period, not just
tiered-group routes.

Not a tracked-baseline performance-regression suite, matching ``tests/benchmark/
test_core_desk_scale.py``'s/``test_qp_scale.py``'s own precedent -- confirming the joint
multi-period path (period-suffixed variable/row construction, the per-period bound-adjustment
walk, the discounted objective) stays fast and correct well beyond a single hand-built fixture, not
stress-testing the solver's absolute scale ceiling. Route/inventory counts mirror
``test_qp_scale.py``'s own 25 x 20 shape; ``_N_PERIODS`` (4 planning periods, 5 periods total
including period 0) is this test's own addition, sizing the dimension that is new here.

Marked ``slow`` (excluded from the default ``pytest tests/ -q`` run via ``addopts`` in
pyproject.toml); run explicitly with ``pytest tests/ -m slow -q``.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta

import pytest

from inventory_optimizer.domain.demand import DemandForecast
from inventory_optimizer.domain.enums import SolverStatus
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.formulation.multi_period import compile_multi_period_lp
from inventory_optimizer.ports.solver import SolverOptions
from inventory_optimizer.solvers.highs import HighsBackend
from inventory_optimizer.validation.solution_verifier import verify_solution

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)

_N_INVENTORY = 25
_ROUTES_PER_INVENTORY = 20
_N_PLANNING_PERIODS = 4  # + period 0 = 5 periods total
_WALL_CLOCK_CEILING_SECONDS = 30.0


def _build_moderate_scale_request() -> OptimizationRequest:
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
        demand.append(
            DemandForecast(
                demand_group_id=f"DG-{i}",
                security_id=f"SEC-{i}",
                borrower_id=f"BORROWER-{i}",
                as_of=_AS_OF,
                reference_quantity_shares=100.0 * _ROUTES_PER_INVENTORY,
                reference_fee_rate=0.02,
                elasticity=0.0,
                source_model="bench",
                source_version="bench-v1",
            )
        )
        for r in range(_ROUTES_PER_INVENTORY):
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

    planning_periods = tuple(
        _EFFECTIVE_DATE + timedelta(days=day) for day in range(1, _N_PLANNING_PERIODS + 1)
    )
    return OptimizationRequest(
        request_id="REQ-MULTI-PERIOD-SCALE-BENCH",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=tuple(inventories),
        routes=tuple(routes),
        demand=tuple(demand),
        planning_periods=planning_periods,
    )


@pytest.mark.slow
def test_multi_period_lp_compile_and_solve_completes_within_time_ceiling(default_config) -> None:
    start = time.perf_counter()
    request = _build_moderate_scale_request()
    problem = compile_multi_period_lp(request, default_config)

    period_count = _N_PLANNING_PERIODS + 1
    n_routes = _N_INVENTORY * _ROUTES_PER_INVENTORY
    expected_vars = 3 * n_routes * period_count + _N_INVENTORY * period_count  # q/inc/dec + a
    assert problem.linear_objective.shape[0] == expected_vars

    result = HighsBackend().solve(problem, SolverOptions())
    report = verify_solution(problem, result)
    elapsed = time.perf_counter() - start

    assert result.status is SolverStatus.OPTIMAL
    assert report.passed is True
    assert elapsed < _WALL_CLOCK_CEILING_SECONDS, (
        f"Multi-period LP scaling benchmark took {elapsed:.1f}s, exceeding the "
        f"{_WALL_CLOCK_CEILING_SECONDS}s generous ceiling -- investigate for a catastrophic "
        "regression (not a tight perf budget)."
    )
