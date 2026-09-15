"""Synthetic Bloomberg adapter tests (specs/0011-bloomberg-data-foundation/: REQ-010)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from inventory_optimizer.adapters.bloomberg.corporate_actions import (
    SyntheticCorporateActionsAdapter,
)
from inventory_optimizer.adapters.bloomberg.field_mapping import ConceptMapping, FieldMapping
from inventory_optimizer.adapters.bloomberg.reference import SyntheticReferenceDataAdapter
from inventory_optimizer.domain.events import (
    CorporateActionEvent,
    CorporateActionStatus,
    CorporateActionType,
)
from inventory_optimizer.domain.reference import (
    DataQuality,
    MarketCalendar,
    PointInTimeValue,
    SecurityReference,
    TradingStatus,
)
from inventory_optimizer.ports.corporate_actions import CorporateActionsPort
from inventory_optimizer.ports.reference_data import ReferenceDataPort

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_MAPPING = FieldMapping(
    version="1",
    concepts={
        "security_reference.trading_status": ConceptMapping(
            mnemonic="EXAMPLE_MNEMONIC",
            unit=None,
            null_policy="reject",
            effective_time_field=None,
            entitlement_id="example-entitlement",
        )
    },
)


def test_synthetic_reference_adapter_satisfies_the_port_protocol() -> None:
    adapter = SyntheticReferenceDataAdapter(field_mapping=_MAPPING)
    assert isinstance(adapter, ReferenceDataPort)


def test_synthetic_reference_adapter_resolves_security_reference() -> None:
    reference = PointInTimeValue[SecurityReference](
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
        effective_to=None,
        source="fixture",
        source_version="v1",
        field_mapping_version="v1",
        quality=DataQuality.VERIFIED,
    )
    adapter = SyntheticReferenceDataAdapter(
        field_mapping=_MAPPING, security_references={"SEC-1": (reference,)}
    )
    found = adapter.get_security_reference("SEC-1", as_of=_T0, known_as_of=_T0)
    assert found is not None
    assert found.value.trading_status == TradingStatus.ACTIVE
    assert adapter.get_security_reference("SEC-UNKNOWN", as_of=_T0, known_as_of=_T0) is None


def test_synthetic_reference_adapter_resolves_market_calendar() -> None:
    calendar = PointInTimeValue[MarketCalendar](
        value=MarketCalendar(market="US", currency="USD"),
        observed_at=_T0,
        effective_from=_T0,
        effective_to=None,
        source="fixture",
        source_version="v1",
        field_mapping_version="v1",
        quality=DataQuality.VERIFIED,
    )
    adapter = SyntheticReferenceDataAdapter(
        field_mapping=_MAPPING, market_calendars={"US": (calendar,)}
    )
    found = adapter.get_market_calendar("US", known_as_of=_T0)
    assert found is not None
    assert found.value.market == "US"


def test_synthetic_corporate_actions_adapter_satisfies_the_port_protocol() -> None:
    adapter = SyntheticCorporateActionsAdapter()
    assert isinstance(adapter, CorporateActionsPort)


def test_synthetic_corporate_actions_adapter_hides_events_not_yet_observed() -> None:
    event = CorporateActionEvent(
        event_id="CA-1",
        version=1,
        event_type=CorporateActionType.DIVIDEND,
        status=CorporateActionStatus.ANNOUNCED,
        affected_security_ids=("SEC-1",),
        announcement_date=date(2026, 1, 5),
    )
    adapter = SyntheticCorporateActionsAdapter(
        events_by_security={"SEC-1": (event,)},
        observed_at_by_event={("CA-1", 1): _T0},
    )
    assert adapter.get_events("SEC-1", known_as_of=_T0) == (event,)
    assert adapter.get_events("SEC-1", known_as_of=datetime(2025, 1, 1, tzinfo=UTC)) == ()
