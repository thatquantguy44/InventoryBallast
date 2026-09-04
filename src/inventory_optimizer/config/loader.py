"""Deterministic layered configuration merge (Section 8.1).

Precedence, lowest to highest:

    package defaults < environment < desk profile < formulation < objective profile
        < policy profile < run/scenario file < explicit CLI/API overrides

Phase 0A has no ``objective``/``policy`` config sections yet (see ``models.py``); their layer slots
exist here so adding them later does not change the merge order or call sites.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.exceptions import ConfigurationError

LAYER_ORDER = (
    "defaults",
    "environment",
    "desk",
    "formulation",
    "objective",
    "policy",
    "run",
    "overrides",
)


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], Mapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_yaml_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigurationError(f"{path}: expected a YAML mapping at the document root")
    return loaded


def merge_layers(**layers: Mapping[str, Any] | None) -> dict[str, Any]:
    """Deep-merge named layers in ``LAYER_ORDER``. Unknown layer names are rejected."""
    unknown = set(layers) - set(LAYER_ORDER)
    if unknown:
        raise ConfigurationError(f"unknown config layer(s): {sorted(unknown)}")

    merged: dict[str, Any] = {}
    for name in LAYER_ORDER:
        layer = layers.get(name)
        if layer:
            merged = _deep_merge(merged, layer)
    return merged


def build_config(**layers: Mapping[str, Any] | None) -> InventoryOptimizerConfig:
    """Merge layers in precedence order and validate into a frozen ``InventoryOptimizerConfig``.

    Unknown keys at any nesting level fail closed (``extra="forbid"`` on every config model).
    """
    merged = merge_layers(**layers)
    try:
        return InventoryOptimizerConfig.model_validate(merged)
    except ValidationError as exc:
        raise ConfigurationError(str(exc)) from exc
