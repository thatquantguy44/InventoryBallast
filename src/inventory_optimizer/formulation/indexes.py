"""Reversible variable/row identity (Section 16.1: "``VariableIndex`` and ``RowIndex`` provide
reversible mappings between domain IDs and solver positions").

Both variables and rows are identified by a ``(kind, scope_id)`` pair rather than hardcoding a
fixed variable/constraint catalog here -- Section 11.3 alone names seven variable kinds (``q``,
``inc``, ``dec``, ``a``, ``d+``, ``d-``, ``m``), most of them optional, and MIP/QP extensions
(T15/T18) add more later. ``kind`` is a free-form string owned by whichever formulation module
introduces it (``formulation/lp.py`` etc.); this module only owns the reversible-mapping mechanics.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Generic, TypeAlias, TypeVar


@dataclass(frozen=True, slots=True)
class VariableKey:
    kind: str
    scope_id: str


@dataclass(frozen=True, slots=True)
class RowKey:
    kind: str
    scope_id: str


K = TypeVar("K")


@dataclass(frozen=True, slots=True)
class ReversibleIndex(Generic[K]):
    """An immutable, order-preserving ``key <-> position`` mapping built once from a finished,
    already-deduplicated key sequence."""

    _positions: Mapping[K, int]
    _keys: tuple[K, ...]

    @classmethod
    def from_keys(cls, keys: Sequence[K]) -> ReversibleIndex[K]:
        positions: dict[K, int] = {}
        for position, key in enumerate(keys):
            if key in positions:
                raise ValueError(f"duplicate index key: {key!r}")
            positions[key] = position
        return cls(_positions=positions, _keys=tuple(keys))

    def position(self, key: K) -> int:
        try:
            return self._positions[key]
        except KeyError as exc:
            raise KeyError(f"unknown index key: {key!r}") from exc

    def key(self, position: int) -> K:
        return self._keys[position]

    def __contains__(self, key: object) -> bool:
        return key in self._positions

    def __len__(self) -> int:
        return len(self._keys)

    @property
    def keys(self) -> tuple[K, ...]:
        return self._keys


VariableIndex: TypeAlias = ReversibleIndex[VariableKey]
RowIndex: TypeAlias = ReversibleIndex[RowKey]
