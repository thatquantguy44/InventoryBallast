"""Expected-economics domain contract tests (specs/0012-expected-economics-realism/: REQ-005)."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from inventory_optimizer.domain.economics import ExpectedEconomics


def _estimate(**overrides: object) -> ExpectedEconomics:
    fields: dict[str, object] = dict(
        route_id="RT-A",
        take_up_probability=0.75,
        conditional_expected_days_active=10.0,
        return_hazard=0.01,
        repricing_hazard=0.02,
        recall_failure_probability=0.03,
        manufactured_payment_cost_usd=0.10,
        indemnification_capital_cost_usd=0.20,
        settlement_fail_cost_usd=0.30,
        relationship_value_or_cost_usd=0.05,
        model_version="fixture-expected-economics-v1",
        calibration_date=date(2026, 1, 1),
        uncertainty=0.12,
    )
    fields.update(overrides)
    return ExpectedEconomics(**fields)


def test_expected_economics_accepts_required_lineage() -> None:
    estimate = _estimate()

    assert estimate.model_version == "fixture-expected-economics-v1"
    assert estimate.calibration_date == date(2026, 1, 1)
    assert estimate.uncertainty == 0.12


def test_expected_economics_is_frozen() -> None:
    estimate = _estimate()

    with pytest.raises(ValidationError):
        estimate.take_up_probability = 0.1  # type: ignore[misc]


def test_expected_economics_rejects_invalid_probability() -> None:
    with pytest.raises(ValidationError):
        _estimate(take_up_probability=1.01)


def test_expected_economics_rejects_non_positive_active_days() -> None:
    with pytest.raises(ValidationError):
        _estimate(conditional_expected_days_active=0.0)


def test_expected_economics_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ExpectedEconomics.model_validate({**_estimate().model_dump(), "extra": 1})
