"""``enrichment.security_master`` tests (specs/0011-bloomberg-data-foundation/: REQ-007,
AC-003)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from inventory_optimizer.domain.reference import (
    DataQuality,
    PointInTimeValue,
    SecurityReference,
    TradingStatus,
)
from inventory_optimizer.enrichment.security_master import reconcile
from inventory_optimizer.exceptions import ReconciliationConflict

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _reference(**overrides: object) -> PointInTimeValue[SecurityReference]:
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
    return PointInTimeValue[SecurityReference](
        value=SecurityReference(**fields),
        observed_at=_T0,
        effective_from=_T0,
        effective_to=None,
        source="bloomberg",
        source_version="v42",
        field_mapping_version="v1",
        quality=DataQuality.VERIFIED,
    )


def test_agreeing_currency_does_not_raise() -> None:
    reconcile("SEC-1", {"currency": "USD"}, _reference(currency="USD"))


def test_conflicting_currency_raises_reconciliation_conflict() -> None:
    """AC-003: raises naming both values and sources, never silently overriding either."""
    with pytest.raises(ReconciliationConflict) as excinfo:
        reconcile("SEC-1", {"currency": "USD"}, _reference(currency="EUR"), internal_source="obb")

    conflict = excinfo.value
    assert conflict.internal_security_id == "SEC-1"
    assert conflict.field == "currency"
    assert conflict.internal_value == "USD"
    assert conflict.internal_source == "obb"
    assert conflict.bloomberg_value == "EUR"
    assert conflict.bloomberg_source_version == "v42"


def test_field_absent_from_internal_fields_is_not_checked() -> None:
    reconcile("SEC-1", {}, _reference(currency="EUR"))
