"""Deterministic variable-index construction (Section 16.5: "sort IDs before building indexes").

Callers (``formulation/lp.py`` and friends, T08+) decide which variable kinds a given formulation
needs -- e.g. ``[("q", route_ids), ("inc", route_ids), ("dec", route_ids), ("a", inventory_ids)]``
-- and in what block order; this module only guarantees each block is sorted and the whole result
is duplicate-free.
"""

from __future__ import annotations

from collections.abc import Sequence

from inventory_optimizer.formulation.indexes import VariableIndex, VariableKey


def build_variable_index(blocks: Sequence[tuple[str, Sequence[str]]]) -> VariableIndex:
    """Build a ``VariableIndex`` from ``(kind, scope_ids)`` blocks, block order preserved and each
    block's ``scope_ids`` sorted independently."""
    keys: list[VariableKey] = []
    for kind, scope_ids in blocks:
        if not kind:
            raise ValueError("variable kind must be non-empty")
        for scope_id in sorted(scope_ids):
            keys.append(VariableKey(kind=kind, scope_id=scope_id))
    return VariableIndex.from_keys(keys)
