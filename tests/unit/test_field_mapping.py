"""``adapters.bloomberg.field_mapping`` tests (specs/0011-bloomberg-data-foundation/: REQ-009,
AC-009)."""

from __future__ import annotations

from pathlib import Path

import pytest

from inventory_optimizer.adapters.bloomberg.field_mapping import load_field_mapping
from inventory_optimizer.exceptions import ConfigurationError

_SHIPPED_EXAMPLE = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "data_sources"
    / "field_mapping.example.yaml"
)


def test_shipped_example_loads() -> None:
    mapping = load_field_mapping(_SHIPPED_EXAMPLE)
    assert mapping.version == "1"
    assert "security_reference.trading_status" in mapping.concepts
    concept = mapping.concept("security_reference.trading_status")
    assert concept.mnemonic
    assert concept.entitlement_id


def test_unknown_concept_raises_configuration_error() -> None:
    mapping = load_field_mapping(_SHIPPED_EXAMPLE)
    with pytest.raises(ConfigurationError):
        mapping.concept("not_a_real_concept")


def test_missing_file_raises_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        load_field_mapping(tmp_path / "does-not-exist.yaml")


def test_malformed_config_raises_configuration_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("not_version_or_concepts: true\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_field_mapping(bad)


def test_version_bump_does_not_rewrite_prior_values(tmp_path: Path) -> None:
    """AC-009: a value produced under an old mapping config keeps its own field_mapping_version;
    loading a bumped config produces a distinctly-versioned mapping object rather than mutating
    the old one."""
    v1_path = tmp_path / "v1.yaml"
    v1_path.write_text(
        "version: '1'\n"
        "concepts:\n"
        "  security_reference.trading_status:\n"
        "    mnemonic: EXAMPLE_MNEMONIC\n"
        "    null_policy: reject\n"
        "    entitlement_id: example-entitlement\n",
        encoding="utf-8",
    )
    v2_path = tmp_path / "v2.yaml"
    v2_path.write_text(
        "version: '2'\n"
        "concepts:\n"
        "  security_reference.trading_status:\n"
        "    mnemonic: EXAMPLE_MNEMONIC_RENAMED\n"
        "    null_policy: reject\n"
        "    entitlement_id: example-entitlement\n",
        encoding="utf-8",
    )
    v1 = load_field_mapping(v1_path)
    v2 = load_field_mapping(v2_path)
    assert v1.version == "1"
    assert v2.version == "2"
    assert v1.concept("security_reference.trading_status").mnemonic == "EXAMPLE_MNEMONIC"
