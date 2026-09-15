"""Synthetic, fixture-backed ``ReferenceDataPort`` implementation (REQ-010).

No network call, no vendor SDK import, no credentials -- constructed directly from hand-authored
``PointInTimeValue`` fixtures (never a captured real Bloomberg response, NFR-004). Structurally
satisfies ``ports.reference_data.ReferenceDataPort`` (``@runtime_checkable``); a real,
entitlement-backed adapter would implement the same port with zero change to any caller.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from inventory_optimizer.adapters.bloomberg.field_mapping import FieldMapping
from inventory_optimizer.domain.reference import MarketCalendar, PointInTimeValue, SecurityReference
from inventory_optimizer.enrichment.point_in_time import resolve_latest_known


class SyntheticReferenceDataAdapter:
    """Holds an in-memory fixture set, keyed by internal security ID / market."""

    def __init__(
        self,
        *,
        field_mapping: FieldMapping,
        security_references: Mapping[str, Sequence[PointInTimeValue[SecurityReference]]] = {},
        market_calendars: Mapping[str, Sequence[PointInTimeValue[MarketCalendar]]] = {},
    ) -> None:
        self._field_mapping = field_mapping
        self._security_references = security_references
        self._market_calendars = market_calendars

    @property
    def field_mapping(self) -> FieldMapping:
        return self._field_mapping

    def get_security_reference(
        self, internal_security_id: str, *, as_of: datetime, known_as_of: datetime
    ) -> PointInTimeValue[SecurityReference] | None:
        return resolve_latest_known(
            self._security_references.get(internal_security_id, ()),
            as_of=as_of,
            known_as_of=known_as_of,
        )

    def get_market_calendar(
        self, market: str, *, known_as_of: datetime
    ) -> PointInTimeValue[MarketCalendar] | None:
        # A calendar's economic effective time and knowledge time collapse to the same moment for
        # this port's purposes: what matters is "the latest calendar version known by now."
        return resolve_latest_known(
            self._market_calendars.get(market, ()),
            as_of=known_as_of,
            known_as_of=known_as_of,
        )
