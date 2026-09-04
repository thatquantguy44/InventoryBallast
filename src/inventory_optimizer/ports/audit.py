"""Audit sink port: injected, never a concrete store (Section 28: "audit sink is an injected
adapter"; Section 21: run audit envelope)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from pydantic import JsonValue


@runtime_checkable
class AuditSink(Protocol):
    def record(self, event: Mapping[str, JsonValue]) -> None:
        """Persist one structured audit event. Must not raise on transient sink failure in a way
        that changes the optimization result; failures are the platform's concern."""
        ...
