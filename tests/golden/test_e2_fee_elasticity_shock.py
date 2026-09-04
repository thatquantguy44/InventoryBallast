"""EXAMPLES.md E2 -- Fee Elasticity Shock.

    Q_ref = 80, F_ref = 0.02, f_scenario = 0.03, epsilon = 0.5
    D(f) = Q_ref * (f / F_ref) ** (-epsilon) = 65.3197264742

The full E2 scenario also checks post-allocation, available shares, and one-day fee revenue, which
require the scenario engine (T13) and LP compiler (T08) respectively; this checks the one piece
that exists today -- the elasticity-adjusted demand cap itself -- against the spec's exact number.
"""

from __future__ import annotations

import pytest

from inventory_optimizer.config.models import ElasticityConfig
from inventory_optimizer.domain.enums import ReasonCode
from inventory_optimizer.elasticity import evaluate_demand_cap


def test_constant_curve_matches_e2_golden_value(demand_factory) -> None:
    forecast = demand_factory(
        "DG-E2",
        "BORROWER-E2",
        fee_rate=0.02,
        reference_quantity_shares=80.0,
        elasticity=0.5,
    )
    result = evaluate_demand_cap(forecast, 0.03, config=ElasticityConfig())

    assert result.raw_demand_shares == pytest.approx(65.3197264742, rel=1e-9)
    assert result.effective_cap_shares == pytest.approx(65.3197264742, rel=1e-9)
    assert result.reason_code is ReasonCode.ELASTICITY_REDUCED_DEMAND
