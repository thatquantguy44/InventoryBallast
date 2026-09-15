"""Entity hierarchy resolver tests (specs/0012-expected-economics-realism/: REQ-002, AC-003)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from inventory_optimizer.domain.reference import (
    DataQuality,
    EntityRelationship,
    PointInTimeValue,
)
from inventory_optimizer.enrichment.entity_hierarchy import (
    HierarchyResolutionStatus,
    resolve_hierarchy,
)

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _relationship(
    *,
    entity_id: str = "BORROWER-1",
    legal_entity_id: str = "LE-1",
    ultimate_parent_id: str = "PARENT-1",
    confidence: float = 0.95,
    observed_at: datetime = _T0,
    effective_from: datetime = _T0,
    quality: DataQuality = DataQuality.VERIFIED,
) -> PointInTimeValue[EntityRelationship]:
    return PointInTimeValue[EntityRelationship](
        value=EntityRelationship(
            entity_id=entity_id,
            legal_entity_id=legal_entity_id,
            ultimate_parent_id=ultimate_parent_id,
            relationship_type="borrower_to_parent",
            ownership_confidence=confidence,
        ),
        observed_at=observed_at,
        effective_from=effective_from,
        effective_to=None,
        source="fixture",
        source_version="v1",
        field_mapping_version="v1",
        quality=quality,
    )


def test_resolve_hierarchy_returns_latest_known_mapping() -> None:
    old = _relationship(legal_entity_id="LE-OLD", ultimate_parent_id="PARENT-OLD")
    new = _relationship(
        legal_entity_id="LE-NEW",
        ultimate_parent_id="PARENT-NEW",
        observed_at=_T0 + timedelta(days=2),
        effective_from=_T0 + timedelta(days=2),
    )

    resolved = resolve_hierarchy(
        "BORROWER-1",
        (old, new),
        as_of=_T0 + timedelta(days=3),
        known_as_of=_T0 + timedelta(days=3),
        minimum_confidence=0.8,
    )

    assert resolved.status is HierarchyResolutionStatus.RESOLVED
    assert resolved.legal_entity_id == "LE-NEW"
    assert resolved.ultimate_parent_id == "PARENT-NEW"


def test_relationship_observed_later_is_invisible() -> None:
    old = _relationship(legal_entity_id="LE-OLD", ultimate_parent_id="PARENT-OLD")
    later_observed = _relationship(
        legal_entity_id="LE-FUTURE",
        ultimate_parent_id="PARENT-FUTURE",
        observed_at=_T0 + timedelta(days=5),
        effective_from=_T0 + timedelta(days=1),
    )

    resolved = resolve_hierarchy(
        "BORROWER-1",
        (old, later_observed),
        as_of=_T0 + timedelta(days=4),
        known_as_of=_T0 + timedelta(days=4),
        minimum_confidence=0.8,
    )

    assert resolved.status is HierarchyResolutionStatus.RESOLVED
    assert resolved.legal_entity_id == "LE-OLD"
    assert resolved.ultimate_parent_id == "PARENT-OLD"


def test_missing_relationship_is_unresolved() -> None:
    resolved = resolve_hierarchy(
        "BORROWER-UNKNOWN",
        (_relationship(),),
        as_of=_T0,
        known_as_of=_T0,
        minimum_confidence=0.8,
    )

    assert resolved.status is HierarchyResolutionStatus.UNRESOLVED
    assert resolved.relationship is None


def test_low_confidence_mapping_is_flagged() -> None:
    resolved = resolve_hierarchy(
        "BORROWER-1",
        (_relationship(confidence=0.25),),
        as_of=_T0,
        known_as_of=_T0,
        minimum_confidence=0.8,
    )

    assert resolved.status is HierarchyResolutionStatus.LOW_CONFIDENCE
    assert resolved.ownership_confidence == 0.25


def test_conflicting_latest_mapping_is_flagged() -> None:
    left = _relationship(legal_entity_id="LE-A", ultimate_parent_id="PARENT-A")
    right = _relationship(legal_entity_id="LE-B", ultimate_parent_id="PARENT-B")

    resolved = resolve_hierarchy(
        "BORROWER-1",
        (left, right),
        as_of=_T0,
        known_as_of=_T0,
        minimum_confidence=0.8,
    )

    assert resolved.status is HierarchyResolutionStatus.CONFLICT
