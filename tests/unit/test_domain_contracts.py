"""Domain contract invariants (Section 9.2-9.5, 9.8 field-level items 3/4/7/11)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from inventory_optimizer.domain.enums import TradeEventType
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.scenarios import TradeEvent


def test_security_inventory_is_frozen(inventory_factory) -> None:
    inventory = inventory_factory()
    with pytest.raises(ValidationError):
        inventory.total_lendable_shares = 200.0  # type: ignore[misc]


def test_security_inventory_rejects_broken_balance_identity(inventory_factory) -> None:
    with pytest.raises(ValidationError):
        inventory_factory(available_to_lend_shares=50.0)  # should be 100.0


def test_security_inventory_rejects_on_loan_exceeding_total(inventory_factory) -> None:
    with pytest.raises(ValidationError):
        inventory_factory(on_loan_shares=150.0, available_to_lend_shares=-50.0)


def test_security_inventory_rejects_non_usd_currency(inventory_factory) -> None:
    with pytest.raises(ValidationError):
        inventory_factory(currency="EUR")


def test_loan_route_rejects_current_exceeding_maximum(route_factory) -> None:
    with pytest.raises(ValidationError):
        route_factory(
            "RT-X",
            "DG-X",
            fee_rate=0.02,
            current_quantity_shares=90.0,
            maximum_quantity_shares=80.0,
        )


def test_loan_route_rejects_maximum_below_hard_minimum(route_factory) -> None:
    with pytest.raises(ValidationError):
        route_factory(
            "RT-X",
            "DG-X",
            fee_rate=0.02,
            hard_minimum_quantity_shares=50.0,
            maximum_quantity_shares=10.0,
        )


def test_loan_route_rejects_revenue_share_out_of_range(route_factory) -> None:
    with pytest.raises(ValidationError):
        route_factory("RT-X", "DG-X", fee_rate=0.02, revenue_share=1.5)


def test_demand_forecast_requires_positive_fee_rate_when_elastic(demand_factory) -> None:
    with pytest.raises(ValidationError):
        demand_factory("DG-X", "BORROWER-X", fee_rate=0.0, elasticity=0.6)


def test_demand_forecast_accepts_empty_candidate_fee_rates_by_default(demand_factory) -> None:
    """specs/0009-discrete-fee-tier-pricing/ REQ-001: absent is the default, and empty is legal."""
    forecast = demand_factory("DG-X", "BORROWER-X", fee_rate=0.02)
    assert forecast.candidate_fee_rates == ()


def test_demand_forecast_rejects_non_positive_candidate_fee_rate(demand_factory) -> None:
    """AC-007."""
    with pytest.raises(ValidationError):
        demand_factory("DG-X", "BORROWER-X", fee_rate=0.02, candidate_fee_rates=(0.0, 0.02))


def test_demand_forecast_rejects_duplicate_candidate_fee_rates(demand_factory) -> None:
    """AC-007."""
    with pytest.raises(ValidationError):
        demand_factory("DG-X", "BORROWER-X", fee_rate=0.02, candidate_fee_rates=(0.02, 0.02))


def test_demand_forecast_rejects_unordered_candidate_fee_rates(demand_factory) -> None:
    """AC-007."""
    with pytest.raises(ValidationError):
        demand_factory("DG-X", "BORROWER-X", fee_rate=0.02, candidate_fee_rates=(0.03, 0.02))


def test_optimization_request_accepts_empty_planning_periods_by_default(e1_request) -> None:
    """specs/0010-multi-period-settlement/ REQ-001: absent is the default."""
    assert e1_request.planning_periods == ()
    assert e1_request.known_future_events == ()


def _revalidate(e1_request, **overrides: object) -> OptimizationRequest:
    """``model_copy(update=...)`` deliberately skips validation (Pydantic v2) -- these tests need
    the model-level validators to actually run, so rebuild through ``model_validate`` instead."""
    return OptimizationRequest.model_validate({**e1_request.model_dump(), **overrides})


def test_optimization_request_rejects_known_future_events_without_periods(e1_request) -> None:
    """AC-002."""
    event = TradeEvent(
        event_id="RECALL-1",
        event_type=TradeEventType.RECALL,
        trade_date=e1_request.effective_date,
        effective_date=e1_request.effective_date + timedelta(days=1),
        settlement_date=e1_request.effective_date + timedelta(days=1),
        quantity_shares=5.0,
        route_id="RT-A",
        source="fixture",
        source_version="v1",
    )
    with pytest.raises(ValidationError):
        _revalidate(e1_request, known_future_events=(event,))


def test_optimization_request_rejects_planning_period_not_after_effective_date(e1_request) -> None:
    with pytest.raises(ValidationError):
        _revalidate(e1_request, planning_periods=(e1_request.effective_date,))


def test_optimization_request_rejects_unordered_planning_periods(e1_request) -> None:
    with pytest.raises(ValidationError):
        _revalidate(
            e1_request,
            planning_periods=(
                e1_request.effective_date + timedelta(days=3),
                e1_request.effective_date + timedelta(days=1),
            ),
        )


def test_optimization_request_rejects_duplicate_planning_periods(e1_request) -> None:
    with pytest.raises(ValidationError):
        _revalidate(
            e1_request,
            planning_periods=(
                e1_request.effective_date + timedelta(days=1),
                e1_request.effective_date + timedelta(days=1),
            ),
        )


def test_demand_forecast_rejects_more_than_max_candidate_fee_tiers(demand_factory) -> None:
    """The zero-padded tier variable-key index only spans 1000 tiers (validated, not assumed --
    specs/0009-discrete-fee-tier-pricing/plan.md's index-stability section)."""
    with pytest.raises(ValidationError):
        demand_factory(
            "DG-X",
            "BORROWER-X",
            fee_rate=0.001,
            candidate_fee_rates=tuple(0.001 * (i + 1) for i in range(1001)),
        )


def test_demand_forecast_allows_zero_fee_rate_when_inelastic(demand_factory) -> None:
    forecast = demand_factory("DG-X", "BORROWER-X", fee_rate=0.0, elasticity=0.0)
    assert forecast.elasticity == 0.0
