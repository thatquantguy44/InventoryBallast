"""Domain contract invariants (Section 9.2-9.5, 9.8 field-level items 3/4/7/11)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


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


def test_demand_forecast_allows_zero_fee_rate_when_inelastic(demand_factory) -> None:
    forecast = demand_factory("DG-X", "BORROWER-X", fee_rate=0.0, elasticity=0.0)
    assert forecast.elasticity == 0.0
