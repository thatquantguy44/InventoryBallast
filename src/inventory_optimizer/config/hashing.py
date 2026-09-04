"""Stable SHA-256 hash of canonical JSON (Section 8.1: "calculates a stable SHA-256 hash of
canonical JSON")."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from inventory_optimizer.config.models import InventoryOptimizerConfig


def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, fixed separators, no whitespace ambiguity."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def config_hash(config: InventoryOptimizerConfig) -> str:
    payload = config.model_dump(mode="json")
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
