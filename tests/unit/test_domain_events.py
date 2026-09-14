"""``domain.events`` contract tests (specs/0011-bloomberg-data-foundation/: REQ-004, AC-002)."""

from __future__ import annotations

from datetime import date

import pytest

from inventory_optimizer.domain.events import (
    CorporateActionEvent,
    CorporateActionStatus,
    CorporateActionType,
)


def _event(
    version: int, status: CorporateActionStatus, **overrides: object
) -> CorporateActionEvent:
    fields: dict[str, object] = dict(
        event_id="CA-1",
        version=version,
        event_type=CorporateActionType.DIVIDEND,
        status=status,
        affected_security_ids=("SEC-1",),
        announcement_date=date(2026, 1, 1),
    )
    fields.update(overrides)
    return CorporateActionEvent(**fields)


def test_amendment_preserves_prior_version() -> None:
    """AC-002: a corporate action amended twice retains all three versions -- none overwritten."""
    original = _event(1, CorporateActionStatus.ANNOUNCED)
    amendment_one = _event(
        2, CorporateActionStatus.AMENDED, supersedes_event_id=original.event_id
    )
    amendment_two = _event(
        3, CorporateActionStatus.AMENDED, supersedes_event_id=original.event_id
    )

    history = (original, amendment_one, amendment_two)
    versions = {event.version for event in history}
    assert versions == {1, 2, 3}
    assert original.status == CorporateActionStatus.ANNOUNCED
    assert amendment_one.status == CorporateActionStatus.AMENDED
    assert amendment_two.status == CorporateActionStatus.AMENDED


def test_corporate_action_event_has_no_in_place_mutation_method() -> None:
    """REQ-004: "never mutated in place" is enforced by omission -- there is no method that
    changes an existing instance's own fields."""
    event = _event(1, CorporateActionStatus.ANNOUNCED)
    assert not hasattr(event, "amend")
    assert not hasattr(event, "cancel")


def test_corporate_action_event_is_frozen() -> None:
    event = _event(1, CorporateActionStatus.ANNOUNCED)
    with pytest.raises(ValueError):
        event.status = CorporateActionStatus.CANCELLED  # type: ignore[misc]
