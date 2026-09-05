"""T15 MIP compiler unit tests (specs/0006-mip-business-rules/): ``compile_lp``'s new rejection
(AC-006), ``needs_mip``'s detection logic, and ``compile_mip``'s row/variable shape per trigger --
mirroring ``test_lp_compiler.py``'s existing per-component style.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

import pytest

from inventory_optimizer.domain.policies import UtilizationPolicy
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import InputValidationError
from inventory_optimizer.formulation.compiler_support import needs_mip
from inventory_optimizer.formulation.indexes import RowKey, VariableKey
from inventory_optimizer.formulation.lp import compile_lp
from inventory_optimizer.formulation.mip import compile_mip

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


@pytest.mark.parametrize(
    "route_overrides",
    [
        {"all_or_none": True},
        {"lot_size_shares": 10.0},
        {"minimum_active_quantity_shares": 5.0},
    ],
)
def test_needs_mip_true_for_each_route_trigger(
    inventory_factory, route_factory, demand_factory, route_overrides
) -> None:
    request = _single_route_request(
        inventory_factory, route_factory, demand_factory, **route_overrides
    )
    assert needs_mip(request) is True


def test_needs_mip_true_for_cardinality_policy(
    inventory_factory, route_factory, demand_factory
) -> None:
    inventory = inventory_factory()
    route = route_factory("RT-A", "DG-A", fee_rate=0.02)
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02)
    policy = UtilizationPolicy(
        policy_id="UP-1",
        inventory_pool_id="POOL-1",
        effective_from=AS_OF,
        maximum_active_routes=1,
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
    assert needs_mip(request) is True


def test_needs_mip_false_for_plain_request(
    inventory_factory, route_factory, demand_factory
) -> None:
    request = _single_route_request(inventory_factory, route_factory, demand_factory)
    assert needs_mip(request) is False


@pytest.mark.parametrize(
    "route_overrides",
    [
        {"all_or_none": True},
        {"lot_size_shares": 10.0},
        {"minimum_active_quantity_shares": 5.0},
    ],
)
def test_compile_lp_rejects_each_mip_trigger(
    inventory_factory, route_factory, demand_factory, default_config, route_overrides
) -> None:
    """AC-006."""
    request = _single_route_request(
        inventory_factory, route_factory, demand_factory, **route_overrides
    )

    with pytest.raises(InputValidationError) as excinfo:
        compile_lp(request, default_config)

    assert all(issue.code == "MIP_REQUIRED" for issue in excinfo.value.issues)


def test_compile_lp_rejects_cardinality_policy(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    inventory = inventory_factory()
    route = route_factory("RT-A", "DG-A", fee_rate=0.02)
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02)
    policy = UtilizationPolicy(
        policy_id="UP-1",
        inventory_pool_id="POOL-1",
        effective_from=AS_OF,
        maximum_active_routes=1,
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

    with pytest.raises(InputValidationError) as excinfo:
        compile_lp(request, default_config)

    assert excinfo.value.issues[0].location == "utilization_policies[0].maximum_active_routes"


def test_all_or_none_row_matches_hand_formula(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    request = _single_route_request(
        inventory_factory, route_factory, demand_factory,
        maximum_quantity_shares=50.0, all_or_none=True,
    )
    problem = compile_mip(request, default_config)

    row = problem.row_index.position(RowKey("all_or_none", "RT-A"))
    assert problem.row_lower[row] == pytest.approx(0.0)
    assert problem.row_upper[row] == pytest.approx(0.0)
    q_col = problem.variable_index.position(VariableKey("q", "RT-A"))
    z_col = problem.variable_index.position(VariableKey("z", "RT-A"))
    assert problem.constraint_matrix[row, q_col] == pytest.approx(1.0)
    assert problem.constraint_matrix[row, z_col] == pytest.approx(-50.0)
    assert problem.integrality[z_col] == 1


def test_lot_size_row_and_bounds_match_hand_formula(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    request = _single_route_request(
        inventory_factory, route_factory, demand_factory,
        maximum_quantity_shares=100.0, lot_size_shares=15.0,
    )
    problem = compile_mip(request, default_config)

    row = problem.row_index.position(RowKey("lot_size", "RT-A"))
    assert problem.row_lower[row] == pytest.approx(0.0)
    assert problem.row_upper[row] == pytest.approx(0.0)
    q_col = problem.variable_index.position(VariableKey("q", "RT-A"))
    n_col = problem.variable_index.position(VariableKey("n", "RT-A"))
    assert problem.constraint_matrix[row, q_col] == pytest.approx(1.0)
    assert problem.constraint_matrix[row, n_col] == pytest.approx(-15.0)
    assert problem.variable_upper[n_col] == pytest.approx(math.floor(100.0 / 15.0))
    assert problem.integrality[n_col] == 1


def test_cardinality_row_matches_hand_formula(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    inventory = inventory_factory()
    route_a = route_factory("RT-A", "DG-A", fee_rate=0.02)
    route_b = route_factory("RT-B", "DG-B", fee_rate=0.01, borrower_id="BORROWER-RT-B")
    demand_a = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02)
    demand_b = demand_factory("DG-B", "BORROWER-RT-B", fee_rate=0.01)
    policy = UtilizationPolicy(
        policy_id="UP-CARD",
        inventory_pool_id="POOL-1",
        effective_from=AS_OF,
        maximum_active_routes=1,
        source="fixture",
        source_version="v1",
    )
    request = OptimizationRequest(
        request_id="REQ-CARD",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route_a, route_b),
        demand=(demand_a, demand_b),
        utilization_policies=(policy,),
    )
    problem = compile_mip(request, default_config)

    row = problem.row_index.position(RowKey("cardinality", "UP-CARD"))
    assert problem.row_upper[row] == pytest.approx(1.0)
    assert problem.row_lower[row] == -math.inf
    z_a = problem.variable_index.position(VariableKey("z", "RT-A"))
    z_b = problem.variable_index.position(VariableKey("z", "RT-B"))
    assert problem.constraint_matrix[row, z_a] == pytest.approx(1.0)
    assert problem.constraint_matrix[row, z_b] == pytest.approx(1.0)
