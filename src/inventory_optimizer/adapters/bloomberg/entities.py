"""Synthetic, fixture-backed ``EntityDataPort`` implementation.

Like ``adapters.bloomberg.reference``, this is intentionally in-memory: no network call, no vendor
SDK import, and no credentials. A real adapter can satisfy the same port later.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from inventory_optimizer.adapters.bloomberg.field_mapping import FieldMapping
from inventory_optimizer.domain.reference import EntityRelationship, PointInTimeValue
from inventory_optimizer.enrichment.point_in_time import resolve_latest_known


class SyntheticEntityDataAdapter:
    """Holds an in-memory fixture set keyed by borrower/entity ID."""

    def __init__(
        self,
        *,
        field_mapping: FieldMapping,
        entity_relationships: Mapping[str, Sequence[PointInTimeValue[EntityRelationship]]] = {},
    ) -> None:
        self._field_mapping = field_mapping
        self._entity_relationships = entity_relationships

    @property
    def field_mapping(self) -> FieldMapping:
        return self._field_mapping

    def get_entity_relationship(
        self, entity_id: str, *, as_of: datetime, known_as_of: datetime
    ) -> PointInTimeValue[EntityRelationship] | None:
        return resolve_latest_known(
            self._entity_relationships.get(entity_id, ()),
            as_of=as_of,
            known_as_of=known_as_of,
        )
