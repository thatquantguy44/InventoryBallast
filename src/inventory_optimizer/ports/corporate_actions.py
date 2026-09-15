"""Corporate-actions port (R0/T20; Section 22.2's adapter-boundary rule): a business-concept
``Protocol`` for fetching corporate-action event history. No concrete backend import --
``adapters/bloomberg/corporate_actions.py`` is the first (synthetic) implementation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from inventory_optimizer.domain.events import CorporateActionEvent


@runtime_checkable
class CorporateActionsPort(Protocol):
    def get_events(
        self, security_id: str, *, known_as_of: datetime
    ) -> Sequence[CorporateActionEvent]:
        """Returns every version of every corporate action affecting ``security_id`` observed at
        or before ``known_as_of`` -- callers resolve "the latest known version" themselves via
        ``enrichment.point_in_time`` semantics applied to ``(event_id, version)`` groups."""
        ...
