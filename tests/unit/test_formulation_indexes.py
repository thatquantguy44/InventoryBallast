"""Reversible index mechanics and deterministic variable/row construction (Section 16.1, 16.5)."""

from __future__ import annotations

import pytest

from inventory_optimizer.formulation.indexes import ReversibleIndex, RowKey, VariableKey
from inventory_optimizer.formulation.rows import RowIndexBuilder
from inventory_optimizer.formulation.variables import build_variable_index


def test_reversible_index_roundtrips_position_and_key() -> None:
    index = ReversibleIndex.from_keys([VariableKey("q", "RT-B"), VariableKey("q", "RT-A")])

    assert len(index) == 2
    assert index.position(VariableKey("q", "RT-B")) == 0
    assert index.key(0) == VariableKey("q", "RT-B")
    assert VariableKey("q", "RT-A") in index
    assert VariableKey("q", "RT-C") not in index


def test_reversible_index_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError):
        ReversibleIndex.from_keys([VariableKey("q", "RT-A"), VariableKey("q", "RT-A")])


def test_reversible_index_unknown_key_raises_keyerror() -> None:
    index = ReversibleIndex.from_keys([VariableKey("q", "RT-A")])
    with pytest.raises(KeyError):
        index.position(VariableKey("q", "RT-NOWHERE"))


def test_build_variable_index_sorts_within_each_block_and_preserves_block_order() -> None:
    index = build_variable_index(
        [("q", ["RT-B", "RT-A"]), ("a", ["INV-2", "INV-1"])]
    )

    assert index.keys == (
        VariableKey("q", "RT-A"),
        VariableKey("q", "RT-B"),
        VariableKey("a", "INV-1"),
        VariableKey("a", "INV-2"),
    )


def test_build_variable_index_rejects_duplicate_key_across_blocks() -> None:
    with pytest.raises(ValueError):
        build_variable_index([("q", ["RT-A"]), ("q", ["RT-A"])])


def test_build_variable_index_rejects_empty_kind() -> None:
    with pytest.raises(ValueError):
        build_variable_index([("", ["RT-A"])])


def test_row_index_builder_assigns_sequential_positions() -> None:
    builder = RowIndexBuilder()
    first = builder.add("inventory_balance", "INV-1")
    second = builder.add("utilization_cap", "INV-1")

    assert (first, second) == (0, 1)
    row_index = builder.build()
    assert row_index.key(0) == RowKey("inventory_balance", "INV-1")
    assert row_index.key(1) == RowKey("utilization_cap", "INV-1")
    assert len(row_index) == 2


def test_row_index_builder_rejects_duplicate_row() -> None:
    builder = RowIndexBuilder()
    builder.add("inventory_balance", "INV-1")
    with pytest.raises(ValueError):
        builder.add("inventory_balance", "INV-1")
