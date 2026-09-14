"""Versioned field-mapping loader (REQ-009; Section 22.2).

Loads a YAML file matching ``configs/data_sources/field_mapping.example.yaml``'s schema into a
frozen ``FieldMapping``. This is the *only* place a mnemonic-shaped string may legitimately appear
in this repository's source outside a fixture file -- and even here, only as configuration data
read from a file, never hard-coded in Python (Section 22.2: "Do not place Bloomberg field
mnemonics in domain or formulation code").
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from inventory_optimizer.exceptions import ConfigurationError


@dataclass(frozen=True, slots=True)
class ConceptMapping:
    """One business concept's vendor mapping: the field mnemonic, its unit/null handling, which
    vendor field carries its effective time, and the entitlement it requires."""

    mnemonic: str
    unit: str | None
    null_policy: str
    effective_time_field: str | None
    entitlement_id: str


@dataclass(frozen=True, slots=True)
class FieldMapping:
    """A versioned bundle of ``ConceptMapping``s. ``version`` is stamped onto every
    ``PointInTimeValue.field_mapping_version`` a mapped value passes through (REQ-001, REQ-009)."""

    version: str
    concepts: dict[str, ConceptMapping]

    def concept(self, name: str) -> ConceptMapping:
        try:
            return self.concepts[name]
        except KeyError as exc:
            raise ConfigurationError(
                f"field mapping {self.version!r} has no entry for concept {name!r}"
            ) from exc


def load_field_mapping(path: Path) -> FieldMapping:
    """Raises ``ConfigurationError`` on a missing file or a schema violation -- never a bare
    ``yaml`` or ``KeyError`` traceback."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigurationError(f"could not read field mapping config {path!r}: {exc}") from exc
    if not isinstance(raw, dict) or "version" not in raw or "concepts" not in raw:
        raise ConfigurationError(
            f"field mapping config {path!r} must be a mapping with 'version' and 'concepts' keys"
        )
    concepts: dict[str, ConceptMapping] = {}
    for name, entry in raw["concepts"].items():
        try:
            concepts[name] = ConceptMapping(
                mnemonic=entry["mnemonic"],
                unit=entry.get("unit"),
                null_policy=entry["null_policy"],
                effective_time_field=entry.get("effective_time_field"),
                entitlement_id=entry["entitlement_id"],
            )
        except KeyError as exc:
            raise ConfigurationError(
                f"field mapping config {path!r}, concept {name!r}: missing required key {exc}"
            ) from exc
    return FieldMapping(version=str(raw["version"]), concepts=concepts)
