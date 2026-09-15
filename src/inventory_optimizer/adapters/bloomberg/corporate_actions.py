"""Synthetic, fixture-backed ``CorporateActionsPort`` implementation (REQ-010).

No network call, no vendor SDK import, no credentials. Returns every version observed at or before
``known_as_of`` -- callers (or ``enrichment.point_in_time``-style resolution over
``(event_id, version)`` groups) decide which version is "latest known."
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from inventory_optimizer.domain.events import CorporateActionEvent


class SyntheticCorporateActionsAdapter:
    def __init__(
        self,
        *,
        events_by_security: Mapping[str, Sequence[CorporateActionEvent]] = {},
        observed_at_by_event: Mapping[tuple[str, int], datetime] = {},
    ) -> None:
        """``observed_at_by_event`` maps ``(event_id, version)`` to the time this synthetic
        adapter "received" that version -- ``CorporateActionEvent`` itself carries no
        ``observed_at`` field (Section 22.3 puts observation time on the envelope, not the
        payload); a real adapter would wrap each version in a ``PointInTimeValue`` instead of
        tracking this out of band, which R0 does not need to do since this port returns raw
        events for the caller to resolve."""
        self._events_by_security = events_by_security
        self._observed_at_by_event = observed_at_by_event

    def get_events(
        self, security_id: str, *, known_as_of: datetime
    ) -> Sequence[CorporateActionEvent]:
        return tuple(
            event
            for event in self._events_by_security.get(security_id, ())
            if self._observed_at_by_event.get((event.event_id, event.version), known_as_of)
            <= known_as_of
        )
