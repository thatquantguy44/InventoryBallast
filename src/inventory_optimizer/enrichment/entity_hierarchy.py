"""Point-in-time borrower hierarchy resolution (specs/0012-expected-economics-realism/).

This module deliberately delegates all effective/known-time filtering to
``enrichment.point_in_time.resolve_latest_known``. The only extra work here is interpreting the
selected relationship for entity-limit aggregation: unresolved, low-confidence, or conflicting.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from inventory_optimizer.domain.reference import (
    DataQuality,
    EntityRelationship,
    PointInTimeValue,
)
from inventory_optimizer.enrichment.point_in_time import resolve_latest_known


class HierarchyResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    LOW_CONFIDENCE = "low_confidence"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class HierarchyResolution:
    entity_id: str
    status: HierarchyResolutionStatus
    relationship: PointInTimeValue[EntityRelationship] | None = None

    @property
    def legal_entity_id(self) -> str | None:
        if self.relationship is None:
            return None
        return self.relationship.value.legal_entity_id

    @property
    def ultimate_parent_id(self) -> str | None:
        if self.relationship is None:
            return None
        return self.relationship.value.ultimate_parent_id

    @property
    def ownership_confidence(self) -> float | None:
        if self.relationship is None:
            return None
        return self.relationship.value.ownership_confidence


def _hierarchy_key(value: PointInTimeValue[EntityRelationship]) -> tuple[str, str]:
    return (value.value.legal_entity_id, value.value.ultimate_parent_id)


def resolve_hierarchy(
    entity_id: str,
    relationships: Iterable[PointInTimeValue[EntityRelationship]],
    *,
    as_of: datetime,
    known_as_of: datetime,
    minimum_confidence: float = 0.0,
) -> HierarchyResolution:
    """Resolve one borrower/entity's hierarchy as known at ``known_as_of`` and effective
    ``as_of``.

    ``resolve_latest_known`` performs the point-in-time selection. Conflict detection only compares
    other latest-known winners after that same resolver has deemed each single candidate eligible.
    """
    entity_relationships = tuple(
        relationship
        for relationship in relationships
        if relationship.value.entity_id == entity_id
    )
    selected = resolve_latest_known(
        entity_relationships,
        as_of=as_of,
        known_as_of=known_as_of,
    )
    if selected is None:
        return HierarchyResolution(entity_id, HierarchyResolutionStatus.UNRESOLVED)

    eligible = tuple(
        relationship
        for relationship in entity_relationships
        if resolve_latest_known(
            (relationship,), as_of=as_of, known_as_of=known_as_of
        )
        is relationship
    )
    latest_key = (selected.effective_from, selected.observed_at)
    competing_latest = tuple(
        relationship
        for relationship in eligible
        if (relationship.effective_from, relationship.observed_at) == latest_key
    )
    if selected.quality is DataQuality.CONFLICTING or len(
        {_hierarchy_key(relationship) for relationship in competing_latest}
    ) > 1:
        return HierarchyResolution(
            entity_id, HierarchyResolutionStatus.CONFLICT, relationship=selected
        )

    if selected.value.ownership_confidence < minimum_confidence:
        return HierarchyResolution(
            entity_id, HierarchyResolutionStatus.LOW_CONFIDENCE, relationship=selected
        )

    return HierarchyResolution(entity_id, HierarchyResolutionStatus.RESOLVED, relationship=selected)
