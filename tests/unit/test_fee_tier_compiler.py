"""T-0009 fee-tier pricing MIP compiler unit tests (specs/0009-discrete-fee-tier-pricing/):
exact row/coefficient shape for the three new row families and the tier_pricing objective delta,
`compile_lp`'s rejection (AC-004), the reserved-separator rejection (AC-008), `demand_cap`'s
tiered-group skip (REQ-010), and an untiered request's variable index staying exactly what it
would be with no tier blocks at all (AC-009) -- mirroring `test_mip_compiler.py`'s own
per-component style.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

import pytest

from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import InputValidationError
from inventory_optimizer.formulation.context import (
    build_context,
    route_tier_scope_id,
    tier_scope_id,
)
from inventory_optimizer.formulation.indexes import RowKey, VariableKey
from inventory_optimizer.formulation.lp import compile_lp
from inventory_optimizer.formulation.mip import compile_mip
from inventory_optimizer.formulation.variables import build_variable_index

AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
EFFECTIVE_DATE = date(2026, 9, 3)
_TIERS = (0.02, 0.03)


def _tiered_request(
    inventory_factory, route_factory, demand_factory, **demand_overrides
) -> OptimizationRequest:
    inventory = inventory_factory()
    route = route_factory("RT-A", "DG-A", fee_rate=0.02)
    fields: dict[str, object] = dict(fee_rate=0.02, candidate_fee_rates=_TIERS)
    fields.update(demand_overrides)
    demand = demand_factory("DG-A", "BORROWER-RT-A", **fields)
    return OptimizationRequest(
        request_id="REQ-1",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )


def test_compile_lp_rejects_tiered_request(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-004."""
    request = _tiered_request(inventory_factory, route_factory, demand_factory)

    with pytest.raises(InputValidationError) as excinfo:
        compile_lp(request, default_config)

    assert any(
        issue.code == "MIP_REQUIRED" and issue.location == "demand[0].candidate_fee_rates"
        for issue in excinfo.value.issues
    )
    assert any("DG-A" in issue.message for issue in excinfo.value.issues)


def test_tier_rows_match_hand_formula(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """Section 12.4's three row families: `tier_select[g]: sum_k z_gk <= 1`,
    `tier_capacity[g,k]: sum_j w_jk - D_gk*z_gk <= 0` (elasticity=0.0 -- the demand_factory
    default -- so D_gk = reference_quantity_shares = 80.0 at every tier, regardless of fee), and
    `tier_split[j]: q_j - sum_k w_jk = 0`."""
    request = _tiered_request(inventory_factory, route_factory, demand_factory)
    problem = compile_mip(request, default_config)

    tier0, tier1 = tier_scope_id("DG-A", 0), tier_scope_id("DG-A", 1)
    w0, w1 = route_tier_scope_id("RT-A", 0), route_tier_scope_id("RT-A", 1)
    t0_col = problem.variable_index.position(VariableKey("t", tier0))
    t1_col = problem.variable_index.position(VariableKey("t", tier1))
    w0_col = problem.variable_index.position(VariableKey("w", w0))
    w1_col = problem.variable_index.position(VariableKey("w", w1))
    q_col = problem.variable_index.position(VariableKey("q", "RT-A"))

    select_row = problem.row_index.position(RowKey("tier_select", "DG-A"))
    assert problem.row_lower[select_row] == -math.inf
    assert problem.row_upper[select_row] == pytest.approx(1.0)
    assert problem.constraint_matrix[select_row, t0_col] == pytest.approx(1.0)
    assert problem.constraint_matrix[select_row, t1_col] == pytest.approx(1.0)

    capacity_row_0 = problem.row_index.position(RowKey("tier_capacity", tier0))
    assert problem.row_lower[capacity_row_0] == -math.inf
    assert problem.row_upper[capacity_row_0] == pytest.approx(0.0)
    assert problem.constraint_matrix[capacity_row_0, w0_col] == pytest.approx(1.0)
    assert problem.constraint_matrix[capacity_row_0, t0_col] == pytest.approx(-80.0)

    capacity_row_1 = problem.row_index.position(RowKey("tier_capacity", tier1))
    assert problem.constraint_matrix[capacity_row_1, w1_col] == pytest.approx(1.0)
    assert problem.constraint_matrix[capacity_row_1, t1_col] == pytest.approx(-80.0)

    split_row = problem.row_index.position(RowKey("tier_split", "RT-A"))
    assert problem.row_lower[split_row] == pytest.approx(0.0)
    assert problem.row_upper[split_row] == pytest.approx(0.0)
    assert problem.constraint_matrix[split_row, q_col] == pytest.approx(1.0)
    assert problem.constraint_matrix[split_row, w0_col] == pytest.approx(-1.0)
    assert problem.constraint_matrix[split_row, w1_col] == pytest.approx(-1.0)

    assert problem.integrality[t0_col] == 1
    assert problem.integrality[t1_col] == 1
    assert problem.integrality[w0_col] == 0
    assert problem.integrality[w1_col] == 0
    assert problem.variable_lower[t0_col] == pytest.approx(0.0)
    assert problem.variable_upper[t0_col] == pytest.approx(1.0)


def test_tier_pricing_objective_matches_hand_formula(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """`revenue_share=1.0`, `variable_cost_rate=0.0` (route_factory defaults); `price_usd=10.0`
    (inventory_factory default); `tau=1/360` (act_360, planning_horizon_days=1, the default
    config). `delta_jk = price*tau*revenue_share*(tier_fee - route.fee_rate)`."""
    request = _tiered_request(inventory_factory, route_factory, demand_factory)
    problem = compile_mip(request, default_config)

    w0_col = problem.variable_index.position(VariableKey("w", route_tier_scope_id("RT-A", 0)))
    w1_col = problem.variable_index.position(VariableKey("w", route_tier_scope_id("RT-A", 1)))

    tau = 1.0 / 360.0
    assert problem.linear_objective[w0_col] == pytest.approx(10.0 * tau * (0.02 - 0.02))
    assert problem.linear_objective[w1_col] == pytest.approx(10.0 * tau * (0.03 - 0.02))


def test_demand_cap_skips_tiered_group(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """REQ-010: the baseline `demand_cap` row must not exist for a tiered group -- its capacity is
    enforced per tier instead, by `tier_capacity`."""
    request = _tiered_request(inventory_factory, route_factory, demand_factory)
    problem = compile_mip(request, default_config)

    assert RowKey("demand_cap", "DG-A") not in problem.row_index


@pytest.mark.parametrize("bad_id_field", ["demand_group_id", "route_id"])
def test_reserved_separator_is_rejected(
    inventory_factory, route_factory, demand_factory, default_config, bad_id_field
) -> None:
    """AC-008: a route or demand-group id containing the reserved `"#"` separator is rejected with
    a structured issue rather than silently producing an ambiguous `(route, tier)`/`(group, tier)`
    variable key."""
    demand_group_id = "DG#A" if bad_id_field == "demand_group_id" else "DG-A"
    route_id = "RT#A" if bad_id_field == "route_id" else "RT-A"
    inventory = inventory_factory()
    route = route_factory(route_id, demand_group_id, fee_rate=0.02)
    demand = demand_factory(
        demand_group_id, "BORROWER-RT-A", fee_rate=0.02, candidate_fee_rates=_TIERS
    )
    request = OptimizationRequest(
        request_id="REQ-SEP",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )

    with pytest.raises(InputValidationError) as excinfo:
        compile_mip(request, default_config)

    assert any(issue.code == "RESERVED_SEPARATOR" for issue in excinfo.value.issues)


def test_untiered_request_index_is_unchanged(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-009: an untiered request's variable index carries no `"t"`/`"w"` keys at all, and every
    `q`/`inc`/`dec`/`a` position is exactly what `build_variable_index` produces with no tier
    blocks appended -- the same empty-block guarantee `specs/0006-mip-business-rules/` established
    for `z`/`n`."""
    inventory = inventory_factory()
    route = route_factory("RT-A", "DG-A", fee_rate=0.02)
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02)
    request = OptimizationRequest(
        request_id="REQ-PLAIN",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )
    context = build_context(request, default_config)

    assert not any(key.kind in ("t", "w") for key in context.variable_index.keys)
    expected = build_variable_index(
        [
            ("q", [r.route_id for r in request.routes]),
            ("inc", [r.route_id for r in request.routes]),
            ("dec", [r.route_id for r in request.routes]),
            ("a", [i.inventory_id for i in request.inventory]),
        ]
    )
    assert context.variable_index.keys == expected.keys
