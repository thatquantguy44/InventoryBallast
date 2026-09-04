"""Incremental row registration.

Unlike variables (all known up front from the request), rows are discovered incrementally as
constraint components run in their deterministic order (Section 15.2). ``RowIndexBuilder`` only
assigns positions and rejects duplicates; ``SparseBuilder`` composes it with coefficient and bound
tracking.
"""

from __future__ import annotations

from inventory_optimizer.formulation.indexes import ReversibleIndex, RowIndex, RowKey


class RowIndexBuilder:
    def __init__(self) -> None:
        self._keys: list[RowKey] = []
        self._positions: dict[RowKey, int] = {}

    def add(self, kind: str, scope_id: str) -> int:
        if not kind:
            raise ValueError("row kind must be non-empty")
        key = RowKey(kind=kind, scope_id=scope_id)
        if key in self._positions:
            raise ValueError(f"duplicate row: {key!r}")
        position = len(self._keys)
        self._keys.append(key)
        self._positions[key] = position
        return position

    def __len__(self) -> int:
        return len(self._keys)

    def build(self) -> RowIndex:
        return ReversibleIndex.from_keys(tuple(self._keys))
