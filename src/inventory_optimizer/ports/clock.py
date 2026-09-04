"""Clock port: injectable time source so tests and scenarios stay deterministic."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Return a timezone-aware current timestamp."""
        ...
