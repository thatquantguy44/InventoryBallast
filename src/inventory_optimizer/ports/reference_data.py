"""Reference-data port (R0/T20; Section 22.2's adapter-boundary rule): a business-concept
``Protocol`` for security identity/status and market-calendar lookups. No concrete backend import
-- ``adapters/bloomberg/reference.py`` is the first (synthetic) implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from inventory_optimizer.domain.reference import MarketCalendar, PointInTimeValue, SecurityReference


@runtime_checkable
class ReferenceDataPort(Protocol):
    def get_security_reference(
        self, internal_security_id: str, *, as_of: datetime, known_as_of: datetime
    ) -> PointInTimeValue[SecurityReference] | None:
        """Returns the latest ``SecurityReference`` known as of ``known_as_of`` and effective at
        ``as_of``, or ``None`` if the port has nothing for this identifier."""
        ...

    def get_market_calendar(
        self, market: str, *, known_as_of: datetime
    ) -> PointInTimeValue[MarketCalendar] | None:
        """Returns the latest ``MarketCalendar`` known as of ``known_as_of`` for ``market``, or
        ``None`` if the port has nothing for this market."""
        ...
