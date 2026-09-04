"""Platform invocation context (T34; Section 17.5)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from inventory_optimizer.domain.enums import ProblemFamily
from inventory_optimizer.platform import PlatformInvocationContext


def _make_context(**overrides: object) -> PlatformInvocationContext:
    fields: dict[str, object] = dict(
        request_id="REQ-1",
        correlation_id="CORR-1",
        idempotency_key="IDEMP-1",
        problem_family=ProblemFamily.SECURITIES_LENDING_INVENTORY,
        as_of=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        authorization_reference="AUTHZ-OPAQUE-REF",
        schema_version="1",
    )
    fields.update(overrides)
    return PlatformInvocationContext(**fields)


def test_context_is_frozen() -> None:
    context = _make_context()
    with pytest.raises(ValidationError):
        context.request_id = "changed"  # type: ignore[misc]


def test_context_serializes_to_plain_json() -> None:
    context = _make_context(platform_tenant_id="TENANT-1", actor_reference="ACTOR-1")
    payload = json.loads(context.model_dump_json())
    assert payload["request_id"] == "REQ-1"
    assert payload["problem_family"] == "securities_lending_inventory"
    assert payload["platform_tenant_id"] == "TENANT-1"


def test_context_roundtrips_through_json() -> None:
    context = _make_context()
    restored = PlatformInvocationContext.model_validate_json(context.model_dump_json())
    assert restored == context


def test_context_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _make_context(platform_session_object={"leaked": "session"})
