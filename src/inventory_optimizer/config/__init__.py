"""Deterministic, frozen configuration (Section 8)."""

from inventory_optimizer.config.hashing import canonical_json, config_hash
from inventory_optimizer.config.loader import build_config, load_yaml_file, merge_layers
from inventory_optimizer.config.models import (
    DeskConfig,
    FormulationConfig,
    InventoryOptimizerConfig,
    ObservabilityConfig,
    SolverConfig,
    ValidationConfig,
)

__all__ = [
    "DeskConfig",
    "FormulationConfig",
    "InventoryOptimizerConfig",
    "ObservabilityConfig",
    "SolverConfig",
    "ValidationConfig",
    "build_config",
    "canonical_json",
    "config_hash",
    "load_yaml_file",
    "merge_layers",
]
