"""Entity-hierarchy port (R1/T22; Section 22.2 adapter-boundary rule).

Business-concept ``Protocol`` for borrower/legal-entity hierarchy lookups. Concrete adapters live
under ``adapters/`` and return point-in-time enriched values, never vendor records.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from inventory_optimizer.domain.reference import EntityRelationship, PointInTimeValue


@runtime_checkable
class EntityDataPort(Protocol):
    def get_entity_relationship(
        self, entity_id: str, *, as_of: datetime, known_as_of: datetime
    ) -> PointInTimeValue[EntityRelationship] | None:
        """Returns the latest relationship known as of ``known_as_of`` and effective at ``as_of``,
        or ``None`` if the port has nothing for this entity."""
        ...
