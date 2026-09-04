"""Configuration layering, unknown-key rejection, and hash determinism (Section 8.1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from inventory_optimizer.config import build_config, config_hash, load_yaml_file
from inventory_optimizer.exceptions import ConfigurationError

DEFAULT_YAML = (
    Path(__file__).resolve().parents[2] / "configs" / "default.yaml"
)


def test_default_yaml_loads_and_validates() -> None:
    defaults = load_yaml_file(DEFAULT_YAML)
    config = build_config(defaults=defaults)
    assert config.formulation.mode.value == "lp"
    assert config.solver.backend == "highs"


def test_higher_precedence_layer_overrides_lower() -> None:
    defaults = load_yaml_file(DEFAULT_YAML)
    config = build_config(
        defaults=defaults,
        environment={"solver": {"backend": "highs", "seed": 1}},
        desk={"solver": {"seed": 2}},
        overrides={"solver": {"seed": 3}},
    )
    assert config.solver.seed == 3


def test_layer_order_is_desk_before_run_before_overrides() -> None:
    defaults = load_yaml_file(DEFAULT_YAML)
    config = build_config(
        defaults=defaults,
        desk={"observability": {"run_id_prefix": "from-desk"}},
        run={"observability": {"run_id_prefix": "from-run"}},
    )
    assert config.observability.run_id_prefix == "from-run"


def test_unknown_top_level_key_is_rejected() -> None:
    defaults = load_yaml_file(DEFAULT_YAML)
    with pytest.raises(ConfigurationError):
        build_config(defaults=defaults, overrides={"not_a_real_section": {}})


def test_unknown_nested_key_is_rejected() -> None:
    defaults = load_yaml_file(DEFAULT_YAML)
    with pytest.raises(ConfigurationError):
        build_config(defaults=defaults, overrides={"solver": {"not_a_real_field": 1}})


def test_unknown_layer_name_is_rejected() -> None:
    defaults = load_yaml_file(DEFAULT_YAML)
    with pytest.raises(ConfigurationError):
        build_config(defaults=defaults, not_a_real_layer={"solver": {"seed": 1}})


def test_hash_is_deterministic_and_sensitive_to_content() -> None:
    defaults = load_yaml_file(DEFAULT_YAML)
    config_a = build_config(defaults=defaults)
    config_b = build_config(defaults=defaults)
    config_c = build_config(defaults=defaults, overrides={"solver": {"seed": 7}})

    assert config_hash(config_a) == config_hash(config_b)
    assert config_hash(config_a) != config_hash(config_c)


def test_config_is_frozen() -> None:
    defaults = load_yaml_file(DEFAULT_YAML)
    config = build_config(defaults=defaults)
    with pytest.raises(ValidationError):
        config.solver.seed = 99  # type: ignore[misc]
