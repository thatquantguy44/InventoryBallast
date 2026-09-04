"""T08 LP compiler: component resolution, route-bound rules, and the constraints/objective terms
not exercised by the E1 golden path (reserve buffer, counterparty limits, ineligible routes,
utilization floor, elasticity-adjusted demand caps).
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

import pytest

from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.domain.policies import CounterpartyLimit, UtilizationPolicy
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import RegistrationError
from inventory_optimizer.formulation.indexes import RowKey, VariableKey
from inventory_optimizer.formulation.lp import compile_lp

AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
EFFECTIVE_DATE = date(2026, 9, 3)


def _single_route_request(inventory_factory, route_factory, demand_factory, **route_overrides):
    inventory = inventory_factory()
    route = route_factory("RT-A", "DG-A", fee_rate=0.02, **route_overrides)
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02)
    return OptimizationRequest(
        request_id="REQ-1",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )


def test_unknown_enabled_component_raises(
    inventory_factory, route_factory, demand_factory, default_config: InventoryOptimizerConfig
) -> None:
    request = _single_route_request(inventory_factory, route_factory, demand_factory)
    config = default_config.model_copy(
        update={"desk": default_config.desk.model_copy(update={"enabled_components": ("nope",)})}
    )
    with pytest.raises(RegistrationError):
        compile_lp(request, config)


def test_ineligible_new_route_gets_zero_upper_bound(
    inventory_factory, route_factory, demand_factory, default_config: InventoryOptimizerConfig
) -> None:
    request = _single_route_request(
        inventory_factory,
        route_factory,
        demand_factory,
        eligible=False,
        current_quantity_shares=0.0,
    )
    problem = compile_lp(request, default_config)
    position = problem.variable_index.position(VariableKey("q", "RT-A"))
    assert problem.variable_upper[position] == 0.0


def test_ineligible_existing_route_is_grandfathered_not_recalled(
    inventory_factory, route_factory, demand_factory, default_config: InventoryOptimizerConfig
) -> None:
    request = _single_route_request(
        inventory_factory,
        route_factory,
        demand_factory,
        eligible=False,
        current_quantity_shares=30.0,
        maximum_quantity_shares=80.0,
    )
    problem = compile_lp(request, default_config)
    position = problem.variable_index.position(VariableKey("q", "RT-A"))
    assert problem.variable_upper[position] == 30.0
    assert problem.variable_lower[position] == 0.0


def test_contractual_floor_survives_ineligibility(
    inventory_factory, route_factory, demand_factory, default_config: InventoryOptimizerConfig
) -> None:
    request = _single_route_request(
        inventory_factory,
        route_factory,
        demand_factory,
        eligible=False,
        current_quantity_shares=30.0,
        hard_minimum_quantity_shares=10.0,
        maximum_quantity_shares=80.0,
    )
    problem = compile_lp(request, default_config)
    position = problem.variable_index.position(VariableKey("q", "RT-A"))
    assert problem.variable_lower[position] == 10.0
    assert problem.variable_upper[position] == 30.0


def test_reserve_buffer_tightens_available_lower_bound(
    inventory_factory, route_factory, demand_factory, default_config: InventoryOptimizerConfig
) -> None:
    inventory = inventory_factory()
    route = route_factory("RT-A", "DG-A", fee_rate=0.02)
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02)
    policy = UtilizationPolicy(
        policy_id="UP-1",
        inventory_pool_id="POOL-1",
        effective_from=AS_OF,
        reserve_buffer_shares=5.0,
        source="fixture",
        source_version="v1",
    )
    request = OptimizationRequest(
        request_id="REQ-1",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
        utilization_policies=(policy,),
    )
    problem = compile_lp(request, default_config)
    position = problem.variable_index.position(VariableKey("a", "INV-1"))
    assert problem.variable_lower[position] == 5.0


def test_utilization_minimum_adds_floor_row(
    inventory_factory, route_factory, demand_factory, default_config: InventoryOptimizerConfig
) -> None:
    inventory = inventory_factory()
    route = route_factory("RT-A", "DG-A", fee_rate=0.02, maximum_quantity_shares=80.0)
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02)
    policy = UtilizationPolicy(
        policy_id="UP-1",
        inventory_pool_id="POOL-1",
        effective_from=AS_OF,
        minimum_utilization=0.10,
        source="fixture",
        source_version="v1",
    )
    request = OptimizationRequest(
        request_id="REQ-1",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
        utilization_policies=(policy,),
    )
    problem = compile_lp(request, default_config)
    row_position = problem.row_index.position(RowKey("utilization_min", "INV-1:UP-1"))
    assert problem.row_lower[row_position] == pytest.approx(10.0)
    assert problem.row_upper[row_position] == math.inf


def test_counterparty_quantity_limit_adds_row(
    inventory_factory, route_factory, demand_factory, default_config: InventoryOptimizerConfig
) -> None:
    inventory = inventory_factory()
    route = route_factory("RT-A", "DG-A", fee_rate=0.02, borrower_id="BORROWER-X")
    demand = demand_factory("DG-A", "BORROWER-X", fee_rate=0.02)
    limit = CounterpartyLimit(
        limit_id="CL-1",
        borrower_id="BORROWER-X",
        effective_from=AS_OF,
        maximum_quantity_shares=40.0,
        source="fixture",
        source_version="v1",
    )
    request = OptimizationRequest(
        request_id="REQ-1",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
        counterparty_limits=(limit,),
    )
    problem = compile_lp(request, default_config)
    row_position = problem.row_index.position(RowKey("counterparty_quantity", "CL-1"))
    assert problem.row_upper[row_position] == 40.0
    col = problem.variable_index.position(VariableKey("q", "RT-A"))
    assert problem.constraint_matrix[row_position, col] == pytest.approx(1.0)


def test_counterparty_notional_limit_uses_price(
    inventory_factory, route_factory, demand_factory, default_config: InventoryOptimizerConfig
) -> None:
    inventory = inventory_factory(price_usd=25.0)
    route = route_factory("RT-A", "DG-A", fee_rate=0.02, borrower_id="BORROWER-X")
    demand = demand_factory("DG-A", "BORROWER-X", fee_rate=0.02)
    limit = CounterpartyLimit(
        limit_id="CL-1",
        borrower_id="BORROWER-X",
        effective_from=AS_OF,
        maximum_notional_usd=1_000.0,
        source="fixture",
        source_version="v1",
    )
    request = OptimizationRequest(
        request_id="REQ-1",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
        counterparty_limits=(limit,),
    )
    problem = compile_lp(request, default_config)
    row_position = problem.row_index.position(RowKey("counterparty_notional", "CL-1"))
    col = problem.variable_index.position(VariableKey("q", "RT-A"))
    assert problem.constraint_matrix[row_position, col] == pytest.approx(25.0)


def test_demand_cap_uses_elasticity_adjusted_value(
    inventory_factory, route_factory, demand_factory, default_config: InventoryOptimizerConfig
) -> None:
    # Same numbers as EXAMPLES.md E2: reference fee 2%, current fee 3%, epsilon=0.5 -> cap
    # shrinks from 80 to 65.3197264742.
    inventory = inventory_factory()
    route = route_factory("RT-A", "DG-A", fee_rate=0.03, maximum_quantity_shares=80.0)
    demand = demand_factory(
        "DG-A", "BORROWER-RT-A", fee_rate=0.02, reference_quantity_shares=80.0, elasticity=0.5
    )
    request = OptimizationRequest(
        request_id="REQ-1",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )
    problem = compile_lp(request, default_config)
    row_position = problem.row_index.position(RowKey("demand_cap", "DG-A"))
    assert problem.row_upper[row_position] == pytest.approx(65.3197264742, rel=1e-9)


def test_fee_revenue_coefficient_matches_hand_formula(
    inventory_factory, route_factory, demand_factory, default_config: InventoryOptimizerConfig
) -> None:
    inventory = inventory_factory(price_usd=10.0)
    route = route_factory(
        "RT-A", "DG-A", fee_rate=0.02, revenue_share=0.8, variable_cost_rate=0.001
    )
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02)
    request = OptimizationRequest(
        request_id="REQ-1",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )
    problem = compile_lp(request, default_config)
    position = problem.variable_index.position(VariableKey("q", "RT-A"))
    tau = 1.0 / 360.0
    expected = 10.0 * tau * (0.02 * 0.8 - 0.001)
    assert problem.linear_objective[position] == pytest.approx(expected)


def test_transition_cost_coefficients_are_negative_on_inc_and_dec(
    inventory_factory, route_factory, demand_factory, default_config: InventoryOptimizerConfig
) -> None:
    inventory = inventory_factory()
    route = route_factory(
        "RT-A",
        "DG-A",
        fee_rate=0.02,
        increase_cost_usd_per_share=0.05,
        decrease_cost_usd_per_share=0.07,
    )
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02)
    request = OptimizationRequest(
        request_id="REQ-1",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )
    problem = compile_lp(request, default_config)
    inc_position = problem.variable_index.position(VariableKey("inc", "RT-A"))
    dec_position = problem.variable_index.position(VariableKey("dec", "RT-A"))
    assert problem.linear_objective[inc_position] == pytest.approx(-0.05)
    assert problem.linear_objective[dec_position] == pytest.approx(-0.07)
