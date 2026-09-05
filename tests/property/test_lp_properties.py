"""Section 24.2 property tests (specs/0005-test-hardening/spec.md).

Every strategy here is deliberately narrow -- a single inventory record, generous per-route
maxima/demand caps, no utilization/counterparty policies -- so the *only* binding constraint is
whatever the property is actually about. A fully generic "any valid request" strategy would need
to encode every cross-record invariant (on-loan reconciliation, demand-group fee/borrower
consistency, balance identity) to avoid constant rejection; these targeted strategies sidestep
that by construction instead (``plan.md``'s design note).

Uses `pytest` fixtures (`inventory_factory`/`route_factory`/`demand_factory`/`default_config`,
from ``tests/conftest.py``) alongside `@given` -- these are stateless factory callables, so reusing
one instance across every generated example (hypothesis does not re-run function-scoped fixtures
per example) is safe; ``suppress_health_check`` acknowledges that explicitly rather than silencing
an unrelated warning.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from inventory_optimizer.domain.enums import TradeEventType
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.scenarios import Scenario, TradeEvent
from inventory_optimizer.elasticity.constant import ConstantElasticityCurve
from inventory_optimizer.elasticity.semilog import SemiLogElasticityCurve
from inventory_optimizer.facade import InventoryOptimizer
from inventory_optimizer.scenarios.runner import run_scenario
from inventory_optimizer.validation.solution_verifier import DEFAULT_TOLERANCE

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)

_PROPERTY_SETTINGS = settings(
    max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)


def _request(inventory, routes, demand) -> OptimizationRequest:
    return OptimizationRequest(
        request_id="REQ-PROP",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=tuple(routes),
        demand=tuple(demand),
    )


@_PROPERTY_SETTINGS
@given(
    total_lendable=st.floats(min_value=10.0, max_value=1000.0),
    n_routes=st.integers(min_value=1, max_value=3),
    fee_rates=st.lists(
        st.floats(min_value=0.001, max_value=0.10), min_size=3, max_size=3, unique=True
    ),
)
def test_conservation_and_non_negativity(
    total_lendable,
    n_routes,
    fee_rates,
    inventory_factory,
    route_factory,
    demand_factory,
    default_config,
) -> None:
    """AC-001 (conservation) + AC-008 (non-negativity), combined: both read the same solve."""
    routes = [
        route_factory(
            f"RT-{i}",
            f"DG-{i}",
            fee_rate=fee_rates[i],
            borrower_id=f"BORROWER-{i}",
            maximum_quantity_shares=total_lendable,
        )
        for i in range(n_routes)
    ]
    demand = [
        demand_factory(
            f"DG-{i}",
            f"BORROWER-{i}",
            fee_rate=fee_rates[i],
            reference_quantity_shares=total_lendable,
        )
        for i in range(n_routes)
    ]
    inventory = inventory_factory(
        total_lendable_shares=total_lendable, available_to_lend_shares=total_lendable
    )
    request = _request(inventory, routes, demand)
    result = InventoryOptimizer(config=default_config).optimize(request)

    assert result.verification.passed is True
    assert result.verification.max_row_violation <= DEFAULT_TOLERANCE

    for allocation in result.allocations:
        assert allocation.post_quantity_shares >= -DEFAULT_TOLERANCE
        assert allocation.increase_shares >= -DEFAULT_TOLERANCE
        assert allocation.decrease_shares >= -DEFAULT_TOLERANCE
    for balance in result.balances:
        assert balance.post_available_shares >= -DEFAULT_TOLERANCE
        assert balance.post_on_loan_shares >= -DEFAULT_TOLERANCE


@_PROPERTY_SETTINGS
@given(
    total_lendable=st.floats(min_value=10.0, max_value=500.0),
    delta=st.floats(min_value=1.0, max_value=100.0),
)
def test_supply_monotonicity(
    total_lendable, delta, inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-002. Single route, ample cap/demand headroom: allocation tracks supply 1:1, so
    increasing supply never decreases it."""

    def _solve(total: float) -> float:
        headroom = total_lendable + delta + 10.0
        route = route_factory(
            "RT-A",
            "DG-A",
            fee_rate=0.02,
            borrower_id="BORROWER-A",
            maximum_quantity_shares=headroom,
        )
        demand = demand_factory(
            "DG-A", "BORROWER-A", fee_rate=0.02, reference_quantity_shares=headroom
        )
        inventory = inventory_factory(total_lendable_shares=total, available_to_lend_shares=total)
        request = _request(inventory, [route], [demand])
        result = InventoryOptimizer(config=default_config).optimize(request)
        return next(a.post_quantity_shares for a in result.allocations if a.route_id == "RT-A")

    low = _solve(total_lendable)
    high = _solve(total_lendable + delta)

    assert high >= low - DEFAULT_TOLERANCE


@_PROPERTY_SETTINGS
@given(
    total_lendable=st.floats(min_value=10.0, max_value=500.0),
    fee_a=st.floats(min_value=0.001, max_value=0.05),
    fee_gap=st.floats(min_value=0.005, max_value=0.05),
    bump=st.floats(min_value=0.005, max_value=0.05),
)
def test_fee_monotonicity(
    total_lendable,
    fee_a,
    fee_gap,
    bump,
    inventory_factory,
    route_factory,
    demand_factory,
    default_config,
) -> None:
    """AC-003. Two routes, one inventory, each able to alone absorb all supply: the higher-fee
    route wins entirely (a step function, but monotonic)."""
    fee_b = fee_a + fee_gap
    assume(abs((fee_a + bump) - fee_b) > 1e-6)  # dodge landing the bumped fee exactly on fee_b

    def _solve(fee_a_value: float) -> dict[str, float]:
        route_a = route_factory(
            "RT-A",
            "DG-A",
            fee_rate=fee_a_value,
            borrower_id="BORROWER-A",
            maximum_quantity_shares=total_lendable,
        )
        route_b = route_factory(
            "RT-B",
            "DG-B",
            fee_rate=fee_b,
            borrower_id="BORROWER-B",
            maximum_quantity_shares=total_lendable,
        )
        demand_a = demand_factory(
            "DG-A", "BORROWER-A", fee_rate=fee_a_value, reference_quantity_shares=total_lendable
        )
        demand_b = demand_factory(
            "DG-B", "BORROWER-B", fee_rate=fee_b, reference_quantity_shares=total_lendable
        )
        inventory = inventory_factory(
            total_lendable_shares=total_lendable, available_to_lend_shares=total_lendable
        )
        request = _request(inventory, [route_a, route_b], [demand_a, demand_b])
        result = InventoryOptimizer(config=default_config).optimize(request)
        return {a.route_id: a.post_quantity_shares for a in result.allocations}

    original = _solve(fee_a)
    assert original["RT-B"] >= original["RT-A"] - DEFAULT_TOLERANCE

    bumped = _solve(fee_a + bump)
    assert bumped["RT-A"] >= original["RT-A"] - DEFAULT_TOLERANCE


@_PROPERTY_SETTINGS
@given(
    elasticity=st.floats(min_value=1e-6, max_value=5.0),
    reference_fee=st.floats(min_value=1e-4, max_value=1.0),
    fee_bump=st.floats(min_value=1e-4, max_value=1.0),
    reference_quantity=st.floats(min_value=1.0, max_value=1000.0),
)
def test_elasticity_monotonicity(elasticity, reference_fee, fee_bump, reference_quantity) -> None:
    """AC-004. Pure curve-formula property, no LP involved."""
    evaluated_fee = reference_fee + fee_bump

    constant_demand = ConstantElasticityCurve().raw_demand(
        reference_quantity=reference_quantity,
        reference_fee=reference_fee,
        evaluated_fee=evaluated_fee,
        elasticity=elasticity,
        fee_floor=1e-9,
    )
    semilog_demand = SemiLogElasticityCurve().raw_demand(
        reference_quantity=reference_quantity,
        reference_fee=reference_fee,
        evaluated_fee=evaluated_fee,
        elasticity=elasticity,
        fee_floor=1e-9,
    )

    assert constant_demand < reference_quantity
    assert semilog_demand < reference_quantity


@_PROPERTY_SETTINGS
@given(n_routes=st.integers(min_value=2, max_value=4), shuffler=st.randoms())
def test_permutation_invariance(
    n_routes, shuffler, inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-005. Allocations are keyed by route_id, so input ordering must not matter."""
    fee_rates = [0.01 + 0.01 * i for i in range(n_routes)]
    routes = [
        route_factory(
            f"RT-{i}",
            f"DG-{i}",
            fee_rate=fee_rates[i],
            borrower_id=f"BORROWER-{i}",
            maximum_quantity_shares=100.0,
        )
        for i in range(n_routes)
    ]
    demand = [
        demand_factory(
            f"DG-{i}", f"BORROWER-{i}", fee_rate=fee_rates[i], reference_quantity_shares=100.0
        )
        for i in range(n_routes)
    ]
    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)

    def _solve(routes_order, demand_order) -> dict[str, float]:
        request = _request(inventory, routes_order, demand_order)
        result = InventoryOptimizer(config=default_config).optimize(request)
        return {a.route_id: a.post_quantity_shares for a in result.allocations}

    original = _solve(routes, demand)
    shuffled_routes = list(routes)
    shuffled_demand = list(demand)
    shuffler.shuffle(shuffled_routes)
    shuffler.shuffle(shuffled_demand)
    shuffled = _solve(shuffled_routes, shuffled_demand)

    assert original.keys() == shuffled.keys()
    for route_id, value in original.items():
        assert value == pytest.approx(shuffled[route_id])


@_PROPERTY_SETTINGS
@given(quantity=st.floats(min_value=1.0, max_value=50.0))
def test_scenario_repeatability(
    quantity, inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-007. Applying and solving the same scenario twice must be identical, modulo the two
    run-identity fields ``ScenarioComparison`` carries (it does not embed `solver.runtime_seconds`
    -- that lives only on the `OptimizationResult`s, which it does not reference by value)."""
    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    route = route_factory("RT-A", "DG-A", fee_rate=0.02, maximum_quantity_shares=100.0)
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02, reference_quantity_shares=100.0)
    request = _request(inventory, [route], [demand])
    optimizer = InventoryOptimizer(config=default_config)
    baseline_result = optimizer.optimize(request)

    event = TradeEvent(
        event_id="SELL-1",
        event_type=TradeEventType.SELL,
        trade_date=_EFFECTIVE_DATE,
        effective_date=_EFFECTIVE_DATE,
        settlement_date=_EFFECTIVE_DATE,
        quantity_shares=quantity,
        inventory_id="INV-1",
        source="fixture",
        source_version="v1",
    )
    scenario = Scenario(scenario_id="S-REPEAT", name="repeat", trade_events=(event,))

    first = run_scenario(request, baseline_result, scenario, optimizer).model_dump(mode="json")
    second = run_scenario(request, baseline_result, scenario, optimizer).model_dump(mode="json")
    for payload in (first, second):
        del payload["baseline_run_id"]
        del payload["scenario_run_id"]

    assert first == second
