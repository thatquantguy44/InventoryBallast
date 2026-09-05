"""Shared ``VerifiedSolution`` fixtures for T11 reporting tests.

``_solve_and_verify`` calls the same public ``formulation.context.build_context`` T12's facade
uses, then wraps the solved, verified request into one ``VerifiedSolution``.

``e1_solution`` is the shared E1 fixture (``EXAMPLES.md``); ``pinned_route_solution`` adds one
route that is contractually pinned at its current quantity (``hard_minimum_quantity_shares ==
maximum_quantity_shares == current_quantity_shares``) so it can never have a material allocation
change, regardless of how attractive its economics look -- the negative fixture AC-007 needs.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.formulation.context import build_context
from inventory_optimizer.formulation.lp import compile_lp
from inventory_optimizer.ports.solver import SolverOptions
from inventory_optimizer.reporting.types import VerifiedSolution
from inventory_optimizer.solvers.highs import HighsBackend
from inventory_optimizer.validation import verify_solution

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)


def _solve_and_verify(
    request: OptimizationRequest, config: InventoryOptimizerConfig
) -> VerifiedSolution:
    context = build_context(request, config)
    problem = compile_lp(request, config)
    result = HighsBackend().solve(problem, SolverOptions())
    verification = verify_solution(problem, result)
    return VerifiedSolution(
        context=context, problem=problem, result=result, verification=verification
    )


@pytest.fixture
def e1_solution(e1_request, default_config) -> VerifiedSolution:
    return _solve_and_verify(e1_request, default_config)


@pytest.fixture
def pinned_route_solution(
    inventory_factory, route_factory, demand_factory, default_config
) -> VerifiedSolution:
    inventory = inventory_factory(
        inventory_id="INV-PINNED",
        total_lendable_shares=120.0,
        available_to_lend_shares=120.0,
    )
    growing_route = route_factory(
        "RT-A", "DG-A", fee_rate=0.02, inventory_id="INV-PINNED", maximum_quantity_shares=100.0
    )
    pinned_route = route_factory(
        "RT-PINNED",
        "DG-P",
        fee_rate=0.05,
        inventory_id="INV-PINNED",
        current_quantity_shares=20.0,
        hard_minimum_quantity_shares=20.0,
        maximum_quantity_shares=20.0,
    )
    demand_a = demand_factory(
        "DG-A", "BORROWER-RT-A", fee_rate=0.02, reference_quantity_shares=100.0
    )
    demand_p = demand_factory(
        "DG-P", "BORROWER-RT-PINNED", fee_rate=0.05, reference_quantity_shares=20.0
    )

    request = OptimizationRequest(
        request_id="REQ-PINNED",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(growing_route, pinned_route),
        demand=(demand_a, demand_p),
    )
    return _solve_and_verify(request, default_config)
