"""``domain.reference`` contract tests (specs/0011-bloomberg-data-foundation/: REQ-001, REQ-002,
REQ-003)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from inventory_optimizer.domain.reference import (
    DataQuality,
    MarketCalendar,
    PointInTimeValue,
    SecurityReference,
    TradingStatus,
)

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_T1 = datetime(2026, 1, 10, tzinfo=UTC)


def _security_reference(**overrides: object) -> SecurityReference:
    fields: dict[str, object] = dict(
        internal_security_id="SEC-1",
        issuer_id="ISS-1",
        instrument_type="equity",
        primary_market="XNYS",
        currency="USD",
        country_of_risk="US",
        trading_status=TradingStatus.ACTIVE,
    )
    fields.update(overrides)
    return SecurityReference(**fields)


def test_point_in_time_value_rejects_effective_to_before_effective_from() -> None:
    with pytest.raises(ValueError):
        PointInTimeValue[SecurityReference](
            value=_security_reference(),
            observed_at=_T0,
            effective_from=_T1,
            effective_to=_T0,
            source="fixture",
            source_version="v1",
            field_mapping_version="v1",
            quality=DataQuality.VERIFIED,
        )


def test_point_in_time_value_accepts_none_effective_to() -> None:
    value = PointInTimeValue[SecurityReference](
        value=_security_reference(),
        observed_at=_T0,
        effective_from=_T0,
        effective_to=None,
        source="fixture",
        source_version="v1",
        field_mapping_version="v1",
        quality=DataQuality.VERIFIED,
    )
    assert value.effective_to is None


def test_security_reference_is_frozen() -> None:
    reference = _security_reference()
    with pytest.raises(ValueError):
        reference.currency = "EUR"  # type: ignore[misc]


def test_security_reference_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        SecurityReference.model_validate({**_security_reference().model_dump(), "extra": 1})


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 1, 5), True),  # Monday, no holiday
        (date(2026, 1, 3), False),  # Saturday
        (date(2026, 1, 4), False),  # Sunday
        (date(2026, 1, 6), False),  # declared settlement holiday
        (date(2026, 1, 7), False),  # exceptional closure
    ],
)
def test_market_calendar_is_settlement_day(day: date, expected: bool) -> None:
    calendar = MarketCalendar(
        market="US",
        currency="USD",
        settlement_holidays=frozenset({date(2026, 1, 6)}),
        exceptional_closures=frozenset({date(2026, 1, 7)}),
    )
    assert calendar.is_settlement_day(day) is expected
