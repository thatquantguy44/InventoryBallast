"""Entity relationship domain contracts (specs/0012-expected-economics-realism/: REQ-001)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from inventory_optimizer.domain.reference import EntityRelationship


def test_entity_relationship_is_frozen() -> None:
    relationship = EntityRelationship(
        entity_id="BORROWER-1",
        legal_entity_id="LE-1",
        ultimate_parent_id="PARENT-1",
        relationship_type="borrower_to_legal_entity",
        ownership_confidence=0.95,
    )

    with pytest.raises(ValidationError):
        relationship.legal_entity_id = "LE-2"  # type: ignore[misc]


def test_entity_relationship_rejects_confidence_outside_unit_interval() -> None:
    with pytest.raises(ValidationError):
        EntityRelationship(
            entity_id="BORROWER-1",
            legal_entity_id="LE-1",
            ultimate_parent_id="PARENT-1",
            relationship_type="borrower_to_legal_entity",
            ownership_confidence=1.1,
        )


def test_entity_relationship_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EntityRelationship.model_validate(
            {
                "entity_id": "BORROWER-1",
                "legal_entity_id": "LE-1",
                "ultimate_parent_id": "PARENT-1",
                "relationship_type": "borrower_to_legal_entity",
                "ownership_confidence": 0.95,
                "extra": "nope",
            }
        )
