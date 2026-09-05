"""Section 14.2's allocation-stability convex QP term, end to end (specs/0007-qp-allocation-
stability/spec.md AC-001 through AC-003, AC-007, AC-008). No `EXAMPLES.md` worked case exists for
any QP scenario (E1-E9 are all continuous-LP/MIP/elasticity/scenario/schedule/collateral/agency-
prime/infeasibility cases) -- these fixtures are hand-constructed and reasoned through in
`plan.md`, the same approach `specs/0006-mip-business-rules/` used for its own MIP golden cases.

All three fixtures share one route: ``fee_revenue_coefficient = price_usd * tau * fee_rate =
10.0 * (1/360) * 0.36 = 0.01`` USD/share (Section 11.12), ``current_quantity_shares=50``,
``maximum_quantity_shares=100``, ample demand/inventory so the LP-only optimum is exactly ``100``.
The closed-form QP optimum (unconstrained by bounds) is ``q0 + fee_coefficient/lambda`` -- derived
in `plan.md` and reproduced here as the exact expected value.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from inventory_optimizer.config.models import ObjectiveConfig
from inventory_optimizer.domain.enums import SolverStatus
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.facade import InventoryOptimizer

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)


def _request(inventory_factory, route_factory, demand_factory) -> OptimizationRequest:
    inventory = inventory_factory(
        total_lendable_shares=100.0, available_to_lend_shares=50.0, on_loan_shares=50.0
    )
    route = route_factory(
        "RT-A",
        "DG-A",
        fee_rate=0.36,
        current_quantity_shares=50.0,
        maximum_quantity_shares=100.0,
    )
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.36, reference_quantity_shares=100.0)
    return OptimizationRequest(
        request_id="REQ-QP",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )


def _config_with_penalty(default_config, penalty: float):
    return default_config.model_copy(
        update={"objective": ObjectiveConfig(allocation_stability_penalty=penalty)}
    )


def test_zero_penalty_matches_lp_behavior(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-001: the default config's penalty is 0.0 -- the LP-equivalent optimum (fill to max)."""
    request = _request(inventory_factory, route_factory, demand_factory)
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    assert result.allocations[0].post_quantity_shares == pytest.approx(100.0, abs=1e-3)


def test_moderate_penalty_pulls_toward_current_book(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-002: closed-form optimum q0 + fee_coefficient/lambda = 50 + 0.01/0.0004 = 75."""
    request = _request(inventory_factory, route_factory, demand_factory)
    config = _config_with_penalty(default_config, 0.0004)
    optimizer = InventoryOptimizer(config=config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    quantity = result.allocations[0].post_quantity_shares
    assert 50.0 < quantity < 100.0
    assert quantity == pytest.approx(75.0, abs=1e-2)


def test_large_penalty_holds_near_current_book(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-003: an overwhelming penalty pulls the optimum back to (approximately) the current
    book."""
    request = _request(inventory_factory, route_factory, demand_factory)
    config = _config_with_penalty(default_config, 1000.0)
    optimizer = InventoryOptimizer(config=config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    assert result.allocations[0].post_quantity_shares == pytest.approx(50.0, abs=1e-2)


def test_attribution_reconciles_and_matches_hand_formula(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-007: build_optimization_result already ran attribute_objective internally -- reaching
    this point without an AttributionMismatchError already proves reconciliation; this test also
    checks the allocation_stability component's own value against the hand formula."""
    request = _request(inventory_factory, route_factory, demand_factory)
    config = _config_with_penalty(default_config, 0.0004)
    optimizer = InventoryOptimizer(config=config)

    result = optimizer.optimize(request)

    quantity = result.allocations[0].post_quantity_shares
    expected_penalty_value = -(0.0004 / 2.0) * (quantity - 50.0) ** 2
    components = {c.component_name: c for c in result.economics.components}
    stability = components["allocation_stability"]
    assert stability.unscaled_value_usd == pytest.approx(expected_penalty_value, abs=1e-4)
    assert stability.baseline_value_usd == pytest.approx(0.0)
    assert result.economics.total_value_usd == pytest.approx(
        components["fee_revenue"].unscaled_value_usd
        + components["transition_cost"].unscaled_value_usd
        + stability.unscaled_value_usd,
        abs=1e-4,
    )


def test_shadow_prices_are_populated_and_correctly_scaled(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-008: a real QP solve (zero integer variables) still reports duals -- and at the fee
    coefficient's own order of magnitude (~0.01), not inflated by the internal scale factor
    (~2500x for this fixture) that would leak through if solvers.highs failed to divide back."""
    request = _request(inventory_factory, route_factory, demand_factory)
    config = _config_with_penalty(default_config, 0.0004)
    optimizer = InventoryOptimizer(config=config)

    result = optimizer.optimize(request)

    dual_values = [c.dual_value for c in result.constraints if c.dual_value is not None]
    assert dual_values  # at least one row reports a dual
    assert all(abs(value) < 1.0 for value in dual_values)
