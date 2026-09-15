"""``enrichment.point_in_time`` tests (specs/0011-bloomberg-data-foundation/: REQ-005, REQ-006,
NFR-003, AC-001, REQ-015)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from inventory_optimizer.domain.reference import (
    DataQuality,
    PointInTimeValue,
    SecurityReference,
    TradingStatus,
)
from inventory_optimizer.enrichment.point_in_time import resolve_latest_known

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _value(
    status: TradingStatus, observed_at: datetime, effective_from: datetime
) -> PointInTimeValue[SecurityReference]:
    return PointInTimeValue[SecurityReference](
        value=SecurityReference(
            internal_security_id="SEC-HALT-1",
            issuer_id="ISS-1",
            instrument_type="equity",
            primary_market="XNYS",
            currency="USD",
            country_of_risk="US",
            trading_status=status,
        ),
        observed_at=observed_at,
        effective_from=effective_from,
        effective_to=None,
        source="fixture",
        source_version="v1",
        field_mapping_version="v1",
        quality=DataQuality.VERIFIED,
    )


def test_future_observed_value_is_invisible_before_known_as_of() -> None:
    """AC-001 / worked fixture from plan.md: a status correction observed later must not be
    visible to a query whose known_as_of predates it, even though it is "more true" by the later
    date -- the entire no-look-ahead guarantee (NFR-003)."""
    later_observed_at = _T0 + timedelta(days=9)
    active = _value(TradingStatus.ACTIVE, observed_at=_T0, effective_from=_T0)
    halted = _value(
        TradingStatus.HALTED, observed_at=later_observed_at, effective_from=later_observed_at
    )

    resolved = resolve_latest_known(
        [active, halted], as_of=_T0 + timedelta(days=4), known_as_of=_T0 + timedelta(days=4)
    )
    assert resolved is not None
    assert resolved.value.trading_status == TradingStatus.ACTIVE


def test_resolution_after_known_as_of_sees_the_later_value() -> None:
    later_observed_at = _T0 + timedelta(days=9)
    active = _value(TradingStatus.ACTIVE, observed_at=_T0, effective_from=_T0)
    halted = _value(
        TradingStatus.HALTED, observed_at=later_observed_at, effective_from=later_observed_at
    )

    resolved = resolve_latest_known(
        [active, halted], as_of=_T0 + timedelta(days=10), known_as_of=_T0 + timedelta(days=10)
    )
    assert resolved is not None
    assert resolved.value.trading_status == TradingStatus.HALTED


def test_no_eligible_candidate_returns_none_not_a_stale_default() -> None:
    value = _value(TradingStatus.ACTIVE, observed_at=_T0, effective_from=_T0)
    resolved = resolve_latest_known([value], as_of=_T0 - timedelta(days=1), known_as_of=_T0)
    assert resolved is None


def test_effective_to_excludes_after_expiry() -> None:
    value = PointInTimeValue[SecurityReference](
        value=SecurityReference(
            internal_security_id="SEC-1",
            issuer_id="ISS-1",
            instrument_type="equity",
            primary_market="XNYS",
            currency="USD",
            country_of_risk="US",
            trading_status=TradingStatus.ACTIVE,
        ),
        observed_at=_T0,
        effective_from=_T0,
        effective_to=_T0 + timedelta(days=1),
        source="fixture",
        source_version="v1",
        field_mapping_version="v1",
        quality=DataQuality.VERIFIED,
    )
    still_effective = resolve_latest_known(
        [value], as_of=_T0 + timedelta(hours=1), known_as_of=_T0
    )
    assert still_effective is not None
    after_expiry = resolve_latest_known(
        [value], as_of=_T0 + timedelta(days=2), known_as_of=_T0 + timedelta(days=2)
    )
    assert after_expiry is None


@given(
    gap_days=st.integers(min_value=1, max_value=365),
    query_offset_days=st.integers(min_value=0, max_value=364),
)
def test_property_resolution_never_sees_a_value_observed_after_known_as_of(
    gap_days: int, query_offset_days: int
) -> None:
    """REQ-015's property test: for any two values of the same concept with different
    observed_at, resolving with known_as_of strictly before the later one's observed_at never
    returns it -- the no-look-ahead guarantee holds for every gap/offset, not just the one worked
    fixture."""
    earlier = _value(TradingStatus.ACTIVE, observed_at=_T0, effective_from=_T0)
    later_observed_at = _T0 + timedelta(days=gap_days)
    later = _value(
        TradingStatus.HALTED, observed_at=later_observed_at, effective_from=later_observed_at
    )

    query_known_as_of = _T0 + timedelta(days=min(query_offset_days, gap_days - 1))
    resolved = resolve_latest_known(
        [earlier, later], as_of=query_known_as_of, known_as_of=query_known_as_of
    )
    # `earlier` is always eligible (effective_from == observed_at == _T0 <= query_known_as_of);
    # the property under test is that `later` -- observed strictly after known_as_of -- is never
    # the one returned.
    assert resolved is earlier
    assert resolved is not later
