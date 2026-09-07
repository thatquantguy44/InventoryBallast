"""Section 12.4's discrete fee-tier pricing MIP, end to end (specs/0009-discrete-fee-tier-pricing/
spec.md AC-001, AC-002, AC-003, AC-005, AC-006, AC-010, plus REQ-009's "at most one tier is ever
selected"). No `EXAMPLES.md` worked case exists for any fee-tier scenario -- these fixtures are
hand-constructed and reasoned through in `plan.md`'s "Worked fixture sketch", the same approach
`specs/0006-mip-business-rules/`/`specs/0007-qp-allocation-stability/` used for their own golden
cases.

Every fixture shares one group, one route (except AC-010's two-route split), `price_usd=10.0`,
`tau=1/360` (`act_360`, `planning_horizon_days=1`, the default config), a constant-elasticity curve
with `Q_ref=100`, `F_ref=0.036` (the incumbent `route.fee_rate`), and candidate tiers
`{0.018, 0.036, 0.072}`. Expected revenue at fee `f` and epsilon `e` is
`P*tau*f*Q_ref*(f/F_ref)**(-e)`, computed exactly in `plan.md`'s table:

    epsilon=0.5: fee 0.018 -> D=141.42, rev=0.0707 | fee 0.036 -> D=100.00, rev=0.1000 |
                 fee 0.072 -> D=70.71, rev=0.1414 (highest tier wins, AC-001)
    epsilon=2.0: fee 0.018 -> D=400.00, rev=0.2000 | fee 0.036 -> D=100.00, rev=0.1000 |
                 fee 0.072 -> D=25.00, rev=0.0500 (lowest tier wins *only with ample supply*,
                 AC-002; with only 100 shares of supply the ranking inverts and the incumbent
                 wins instead, AC-003 -- plan.md's flagged supply-sufficiency trap).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from inventory_optimizer.domain.demand import DemandForecast
from inventory_optimizer.domain.enums import SolverStatus
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.facade import InventoryOptimizer
from inventory_optimizer.formulation.context import tier_scope_id
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.mip import compile_mip
from inventory_optimizer.ports.solver import SolverOptions
from inventory_optimizer.solvers.highs import HighsBackend

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)
_TIERS = (0.018, 0.036, 0.072)


def _single_route_request(
    inventory_factory,
    route_factory,
    demand_factory,
    *,
    total_shares: float,
    elasticity: float,
) -> OptimizationRequest:
    inventory = inventory_factory(total_lendable_shares=total_shares, available_to_lend_shares=total_shares)
    route = route_factory(
        "RT-A", "DG-A", fee_rate=0.036, maximum_quantity_shares=total_shares,
        borrower_id="BORROWER-A",
    )
    demand = demand_factory(
        "DG-A",
        "BORROWER-A",
        fee_rate=0.036,
        reference_quantity_shares=100.0,
        elasticity=elasticity,
        candidate_fee_rates=_TIERS,
    )
    return OptimizationRequest(
        request_id="REQ-FEE-TIER",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )


def test_reprices_up_when_demand_is_inelastic(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-001: epsilon=0.5, ample supply -- the elastic revenue optimum is the *highest* candidate
    tier (0.072), despite the lower volume it implies."""
    request = _single_route_request(
        inventory_factory, route_factory, demand_factory, total_shares=200.0, elasticity=0.5
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    assert result.pricing[0].selected_tier_index == 2
    assert result.pricing[0].selected_fee_rate == pytest.approx(0.072)
    assert result.allocations[0].post_quantity_shares == pytest.approx(70.71067811865476, rel=1e-6)


def test_reprices_down_for_volume_when_elastic(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-002: epsilon=2.0 with ample supply (>=400 shares, plan.md's flagged trap) -- the elastic
    revenue optimum is the *lowest* candidate tier (0.018), won through volume."""
    request = _single_route_request(
        inventory_factory, route_factory, demand_factory, total_shares=500.0, elasticity=2.0
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    assert result.pricing[0].selected_tier_index == 0
    assert result.pricing[0].selected_fee_rate == pytest.approx(0.018)
    assert result.allocations[0].post_quantity_shares == pytest.approx(400.0, rel=1e-6)
    assert result.economics.total_value_usd == pytest.approx(0.2, rel=1e-6)


def test_incumbent_tier_wins_when_supply_is_scarce(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-003: the same epsilon=2.0 elasticity, but only 100 shares of supply -- cutting price
    cannot buy volume that does not exist, and raising it sheds more demand than it gains, so the
    model holds at the incumbent 0.036 tier. Total objective must equal what an untiered solve of
    the same economics produces (NFR-001's reconciliation, restated as AC-003)."""
    request = _single_route_request(
        inventory_factory, route_factory, demand_factory, total_shares=100.0, elasticity=2.0
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    assert result.pricing[0].selected_tier_index == 1
    assert result.pricing[0].selected_fee_rate == pytest.approx(0.036)
    assert result.allocations[0].post_quantity_shares == pytest.approx(100.0, rel=1e-6)

    untiered_inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    untiered_route = route_factory(
        "RT-A", "DG-A", fee_rate=0.036, maximum_quantity_shares=100.0, borrower_id="BORROWER-A",
    )
    untiered_demand = DemandForecast(
        demand_group_id="DG-A",
        security_id="SEC-1",
        borrower_id="BORROWER-A",
        as_of=_AS_OF,
        reference_quantity_shares=100.0,
        reference_fee_rate=0.036,
        elasticity=2.0,
        source_model="fixture",
        source_version="fixture-v1",
    )
    untiered_request = OptimizationRequest(
        request_id="REQ-FEE-TIER-UNTIERED",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(untiered_inventory,),
        routes=(untiered_route,),
        demand=(untiered_demand,),
    )
    untiered_result = optimizer.optimize(untiered_request)

    assert result.economics.total_value_usd == pytest.approx(
        untiered_result.economics.total_value_usd, rel=1e-6
    )


def test_result_reports_menu_and_selection(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-005/NFR-004: the result discloses the full candidate menu alongside the selection, not
    just the winning fee."""
    request = _single_route_request(
        inventory_factory, route_factory, demand_factory, total_shares=200.0, elasticity=0.5
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert len(result.pricing) == 1
    selection = result.pricing[0]
    assert selection.demand_group_id == "DG-A"
    assert selection.reference_fee_rate == pytest.approx(0.036)
    assert selection.candidate_fee_rates == _TIERS
    assert selection.selected_fee_rate == pytest.approx(0.072)
    assert selection.selected_tier_index == 2
    assert selection.filled_shares == pytest.approx(70.71067811865476, rel=1e-6)


def test_attribution_reconciles_and_matches_hand_delta(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-006: build_optimization_result already ran attribute_objective internally -- reaching
    this point without an AttributionMismatchError already proves reconciliation; this test also
    checks tier_pricing's own value against the hand-computed delta between the selected and
    reference fees."""
    request = _single_route_request(
        inventory_factory, route_factory, demand_factory, total_shares=200.0, elasticity=0.5
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    quantity = result.allocations[0].post_quantity_shares
    tau = 1.0 / 360.0
    expected_delta = 10.0 * tau * 1.0 * (0.072 - 0.036) * quantity
    components = {c.component_name: c for c in result.economics.components}
    tier_pricing = components["tier_pricing"]
    assert tier_pricing.unscaled_value_usd == pytest.approx(expected_delta, rel=1e-6)
    assert tier_pricing.baseline_value_usd == pytest.approx(0.0)
    assert result.economics.total_value_usd == pytest.approx(
        components["fee_revenue"].unscaled_value_usd
        + components["transition_cost"].unscaled_value_usd
        + tier_pricing.unscaled_value_usd,
        rel=1e-6,
    )


def test_route_revenue_shares_honored_at_selected_tier(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-010: two routes in one tiered group with different revenue_share -- each route's economics
    are valued at *its own* share against the selected tier fee, not one group-level rate. Each
    route's own maximum_quantity_shares (40) is below the winning tier's 70.71-share group cap, so
    the split between them is fully determined: the higher-revenue_share route (RT-A) fills to its
    own cap first, and the remainder lands on RT-B."""
    inventory_a = inventory_factory(
        inventory_id="INV-A", total_lendable_shares=40.0, available_to_lend_shares=40.0
    )
    inventory_b = inventory_factory(
        inventory_id="INV-B", total_lendable_shares=40.0, available_to_lend_shares=40.0
    )
    route_a = route_factory(
        "RT-A", "DG-A", fee_rate=0.036, inventory_id="INV-A",
        borrower_id="BORROWER-A", maximum_quantity_shares=40.0, revenue_share=1.0,
    )
    route_b = route_factory(
        "RT-B", "DG-A", fee_rate=0.036, inventory_id="INV-B",
        borrower_id="BORROWER-A", maximum_quantity_shares=40.0, revenue_share=0.5,
    )
    demand = demand_factory(
        "DG-A", "BORROWER-A", fee_rate=0.036,
        reference_quantity_shares=100.0, elasticity=0.5, candidate_fee_rates=_TIERS,
    )
    request = OptimizationRequest(
        request_id="REQ-FEE-TIER-SHARES",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory_a, inventory_b),
        routes=(route_a, route_b),
        demand=(demand,),
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True
    assert result.pricing[0].selected_tier_index == 2

    quantities = {a.route_id: a.post_quantity_shares for a in result.allocations}
    assert quantities["RT-A"] == pytest.approx(40.0, rel=1e-6)
    assert quantities["RT-A"] + quantities["RT-B"] == pytest.approx(
        result.pricing[0].filled_shares, rel=1e-6
    )

    tau = 1.0 / 360.0
    expected_tier_pricing = tau * 10.0 * (
        1.0 * (0.072 - 0.036) * quantities["RT-A"] + 0.5 * (0.072 - 0.036) * quantities["RT-B"]
    )
    components = {c.component_name: c for c in result.economics.components}
    assert components["tier_pricing"].unscaled_value_usd == pytest.approx(
        expected_tier_pricing, rel=1e-6
    )


def test_at_most_one_tier_is_ever_selected(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """REQ-009: `tier_select[g]: sum_k z_gk <= 1` is a real, solver-enforced row -- checked directly
    against the raw compiled/solved primal, not merely inferred from `PricingSelection` (which can
    only ever report one tier by construction)."""
    request = _single_route_request(
        inventory_factory, route_factory, demand_factory, total_shares=200.0, elasticity=0.5
    )
    problem = compile_mip(request, default_config)
    result = HighsBackend().solve(problem, SolverOptions())
    assert result.status is SolverStatus.OPTIMAL

    t_values = [
        result.primal[problem.variable_index.position(VariableKey("t", tier_scope_id("DG-A", k)))]
        for k in range(len(_TIERS))
    ]
    assert sum(t_values) <= 1.0 + 1e-6
    assert sum(1 for value in t_values if value > 0.5) <= 1
