"""Elasticity service (T06; Section 12) unit behavior.

The E2 golden check lives in ``tests/golden/test_e2_fee_elasticity_shock.py``.
"""

from __future__ import annotations

import math

import pytest

from inventory_optimizer.config.models import ElasticityConfig
from inventory_optimizer.domain.enums import ElasticityCurveType
from inventory_optimizer.elasticity import evaluate_demand_cap


def test_zero_elasticity_is_price_insensitive(demand_factory) -> None:
    forecast = demand_factory(
        "DG-X",
        "BORROWER-X",
        fee_rate=0.0,
        reference_quantity_shares=80.0,
        elasticity=0.0,
    )
    result = evaluate_demand_cap(forecast, 0.05, config=ElasticityConfig())

    assert result.raw_demand_shares == 80.0
    assert result.reason_code is None


def test_reason_code_absent_when_fee_is_unchanged(demand_factory) -> None:
    forecast = demand_factory(
        "DG-X", "BORROWER-X", fee_rate=0.02, reference_quantity_shares=80.0, elasticity=0.5
    )
    result = evaluate_demand_cap(forecast, 0.02, config=ElasticityConfig())

    assert result.effective_cap_shares == pytest.approx(80.0)
    assert result.reason_code is None


def test_reason_code_absent_when_fee_decreases(demand_factory) -> None:
    forecast = demand_factory(
        "DG-X", "BORROWER-X", fee_rate=0.02, reference_quantity_shares=80.0, elasticity=0.5
    )
    result = evaluate_demand_cap(forecast, 0.01, config=ElasticityConfig())

    assert result.effective_cap_shares > 80.0
    assert result.reason_code is None


def test_fee_floor_prevents_non_positive_fee_from_entering_power_formula(demand_factory) -> None:
    config = ElasticityConfig(fee_floor=1e-6)
    forecast = demand_factory(
        "DG-X", "BORROWER-X", fee_rate=0.02, reference_quantity_shares=80.0, elasticity=0.5
    )

    result = evaluate_demand_cap(forecast, 0.0, config=config)

    expected = 80.0 * (1e-6 / 0.02) ** (-0.5)
    assert result.raw_demand_shares == pytest.approx(expected)


def test_uncertainty_haircut_clips_at_zero(demand_factory) -> None:
    forecast = demand_factory(
        "DG-X",
        "BORROWER-X",
        fee_rate=0.02,
        reference_quantity_shares=10.0,
        elasticity=0.0,
        forecast_std_shares=50.0,
    )
    config = ElasticityConfig(uncertainty_haircut_sigma=1.0)
    result = evaluate_demand_cap(forecast, 0.02, config=config)

    assert result.raw_demand_shares == 10.0
    assert result.uncertainty_haircut_shares == pytest.approx(50.0)
    assert result.effective_cap_shares == 0.0


def test_hard_max_caps_effective_demand(demand_factory) -> None:
    forecast = demand_factory(
        "DG-X",
        "BORROWER-X",
        fee_rate=0.02,
        reference_quantity_shares=80.0,
        elasticity=0.0,
        hard_max_quantity_shares=50.0,
    )
    result = evaluate_demand_cap(forecast, 0.02, config=ElasticityConfig())

    assert result.raw_demand_shares == 80.0
    assert result.effective_cap_shares == 50.0


def test_semilog_curve_matches_manual_formula(demand_factory) -> None:
    forecast = demand_factory(
        "DG-X", "BORROWER-X", fee_rate=0.02, reference_quantity_shares=80.0, elasticity=25.0
    )
    config = ElasticityConfig(curve=ElasticityCurveType.SEMILOG)

    result = evaluate_demand_cap(forecast, 0.03, config=config)

    expected = 80.0 * math.exp(-25.0 * (0.03 - 0.02))
    assert result.raw_demand_shares == pytest.approx(expected)
