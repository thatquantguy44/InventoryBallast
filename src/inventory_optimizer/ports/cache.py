"""Result cache port supporting idempotent replay (Section 17.5): a valid duplicate idempotency
key with the same canonical request/config hash returns the same completed result."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from inventory_optimizer.domain.results import OptimizationResult


@runtime_checkable
class ResultCache(Protocol):
    def get(self, idempotency_key: str, request_hash: str) -> OptimizationResult | None:
        """Return the cached result only if ``request_hash`` matches the original request."""
        ...

    def put(self, idempotency_key: str, request_hash: str, result: OptimizationResult) -> None: ...
