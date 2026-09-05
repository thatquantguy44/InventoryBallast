"""Section 14.1 MIP business rules, end to end (specs/0006-mip-business-rules/spec.md AC-001
through AC-004, AC-008, AC-009). No `EXAMPLES.md` worked case exists for any MIP scenario (E1-E9
are all continuous-LP/elasticity/scenario/schedule/collateral/agency-prime/infeasibility cases) --
these fixtures are hand-constructed and reasoned through in `plan.md`, the same approach
`specs/0005-test-hardening/` used for its two ungrounded golden cases.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime

import pytest

from inventory_optimizer.domain.enums import SolverStatus
from inventory_optimizer.domain.policies import UtilizationPolicy
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.facade import InventoryOptimizer
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.mip import compile_mip
from inventory_optimizer.ports.solver import SolverOptions
from inventory_optimizer.solvers.highs import HighsBackend
from inventory_optimizer.validation.solution_verifier import verify_solution

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)


def test_all_or_none_never_partially_fills(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-001, AC-007."""
    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    route = route_factory(
        "RT-A", "DG-A", fee_rate=0.02, maximum_quantity_shares=50.0, all_or_none=True
    )
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02, reference_quantity_shares=50.0)
    request = OptimizationRequest(
        request_id="REQ-AON",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    quantity = result.allocations[0].post_quantity_shares
    assert quantity == pytest.approx(0.0) or quantity == pytest.approx(50.0)
    assert quantity == pytest.approx(50.0)  # positive economics: fully fills, never partial


def test_all_or_none_can_choose_zero_when_uneconomic(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """The binary genuinely can choose 0, not just always fill -- variable cost exceeds fee."""
    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    route = route_factory(
        "RT-A",
        "DG-A",
        fee_rate=0.001,
        variable_cost_rate=0.05,
        maximum_quantity_shares=50.0,
        all_or_none=True,
    )
    demand = demand_factory(
        "DG-A", "BORROWER-RT-A", fee_rate=0.001, reference_quantity_shares=50.0
    )
    request = OptimizationRequest(
        request_id="REQ-AON-ZERO",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.allocations[0].post_quantity_shares == pytest.approx(0.0)


def test_minimum_ticket_never_partially_activates(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-002. Demand caps the route at 50 shares -- strictly between the 20-share minimum ticket
    and the 80-share maximum, proving the "active" range (not just the 0/full-fill boundary)
    works."""
    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    route = route_factory(
        "RT-B",
        "DG-B",
        fee_rate=0.02,
        maximum_quantity_shares=80.0,
        minimum_active_quantity_shares=20.0,
    )
    demand = demand_factory("DG-B", "BORROWER-RT-B", fee_rate=0.02, reference_quantity_shares=50.0)
    request = OptimizationRequest(
        request_id="REQ-MINTICK",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    quantity = result.allocations[0].post_quantity_shares
    assert quantity == pytest.approx(0.0) or quantity >= 20.0 - 1e-6
    assert quantity == pytest.approx(50.0)


def test_lot_size_quantity_is_exact_multiple(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-003."""
    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    route = route_factory(
        "RT-C", "DG-C", fee_rate=0.02, maximum_quantity_shares=100.0, lot_size_shares=15.0
    )
    demand = demand_factory("DG-C", "BORROWER-RT-C", fee_rate=0.02, reference_quantity_shares=100.0)
    request = OptimizationRequest(
        request_id="REQ-LOT",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    quantity = result.allocations[0].post_quantity_shares
    assert quantity == pytest.approx(90.0)  # floor(100/15) * 15
    remainder = quantity % 15.0
    assert remainder == pytest.approx(0.0, abs=1e-6) or remainder == pytest.approx(15.0, abs=1e-6)


def test_cardinality_limits_active_routes(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-004. Three routes, each capped at 40 shares (so no single route -- nor any two with the
    lowest-fee one -- could ever passively look identical to "just pick the best two"); 90 shares
    of inventory means the two highest-fee routes together (80) cannot fully use supply either,
    proving the solver optimizes the *set* rather than defaulting to some other tie-break."""
    inventory = inventory_factory(
        inventory_id="INV-CARD", total_lendable_shares=90.0, available_to_lend_shares=90.0
    )
    routes = tuple(
        route_factory(
            f"RT-{i}",
            f"DG-{i}",
            fee_rate=0.03 - 0.01 * i,
            inventory_id="INV-CARD",
            borrower_id=f"BORROWER-{i}",
            maximum_quantity_shares=40.0,
        )
        for i in range(3)
    )
    demand = tuple(
        demand_factory(
            f"DG-{i}", f"BORROWER-{i}", fee_rate=0.03 - 0.01 * i, reference_quantity_shares=40.0
        )
        for i in range(3)
    )
    policy = UtilizationPolicy(
        policy_id="UP-CARD",
        inventory_pool_id="POOL-1",
        effective_from=_AS_OF,
        maximum_active_routes=2,
        source="fixture",
        source_version="v1",
    )
    request = OptimizationRequest(
        request_id="REQ-CARD",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=routes,
        demand=demand,
        utilization_policies=(policy,),
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    active = [a for a in result.allocations if a.post_quantity_shares > 1e-6]
    assert len(active) == 2
    active_ids = {a.route_id for a in active}
    assert active_ids == {"RT-0", "RT-1"}  # the two highest-fee routes, not an arbitrary pair


def test_integrality_violation_caught_on_real_mip(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-008: complements the existing synthetic-array test in test_solution_verifier.py by
    exercising a *real* compiled MIP's integrality array end to end."""
    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    route = route_factory(
        "RT-C", "DG-C", fee_rate=0.02, maximum_quantity_shares=100.0, lot_size_shares=15.0
    )
    demand = demand_factory("DG-C", "BORROWER-RT-C", fee_rate=0.02, reference_quantity_shares=100.0)
    request = OptimizationRequest(
        request_id="REQ-LOT-CORRUPT",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )
    problem = compile_mip(request, default_config)
    result = HighsBackend().solve(problem, SolverOptions())
    assert result.status is SolverStatus.OPTIMAL

    n_position = problem.variable_index.position(VariableKey("n", "RT-C"))
    corrupted_primal = result.primal.copy()
    corrupted_primal[n_position] += 0.5
    corrupted = dataclasses.replace(result, primal=corrupted_primal)

    report = verify_solution(problem, corrupted)

    assert report.passed is False
    assert report.max_integrality_violation == pytest.approx(0.5)


def test_no_shadow_prices_for_real_mip_solve(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-009."""
    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    route = route_factory(
        "RT-A", "DG-A", fee_rate=0.02, maximum_quantity_shares=50.0, all_or_none=True
    )
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02, reference_quantity_shares=50.0)
    request = OptimizationRequest(
        request_id="REQ-AON-SHADOW",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.constraints  # rows are still reported...
    assert all(entry.dual_value is None for entry in result.constraints)  # ...but never a dual
