"""Public API facade (T12; Section 17.1): ``InventoryOptimizer`` + ``load_config``.

``InventoryOptimizer.optimize()`` composes five already-implemented, already-tested stages in a
fixed order -- ``validation.raise_if_invalid`` -> ``formulation.context.build_context`` ->
``formulation.lp.compile_lp`` -> the configured ``ports.solver.SolverBackend.solve`` ->
``validation.solution_verifier.verify_solution`` -> ``reporting.result_builder.
build_optimization_result`` -- without re-deriving any of their internal logic. This module is the
one place in this spec's surface that is intentionally impure (wall clock, ``uuid4``): T11's
``build_optimization_result`` deliberately left ``run_id``/``created_at``/``config_hash``/
``input_hash`` as caller-supplied keyword arguments precisely so that function itself could stay
pure; this is the caller.

``load_config`` is a thin, honestly-scoped wrapper over ``config.build_config``/
``config.load_yaml_file`` -- not the full five-axis named-profile resolution Section 17.1
illustrates (``environment=``/``objective=``/``policy=`` have no config section or profile files to
resolve yet; see ``specs/0003-public-api-cli/spec.md``'s Non-Goals).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inventory_optimizer.config.hashing import canonical_json, config_hash
from inventory_optimizer.config.loader import build_config, load_yaml_file
from inventory_optimizer.config.models import InventoryOptimizerConfig, SolverConfig
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.results import OptimizationResult
from inventory_optimizer.exceptions import ConfigurationError
from inventory_optimizer.formulation.context import build_context
from inventory_optimizer.formulation.lp import compile_lp
from inventory_optimizer.platform.context import PlatformInvocationContext
from inventory_optimizer.ports.solver import SolverBackend, SolverOptions
from inventory_optimizer.reporting.result_builder import build_optimization_result
from inventory_optimizer.reporting.types import VerifiedSolution
from inventory_optimizer.validation import raise_if_invalid
from inventory_optimizer.validation.solution_verifier import verify_solution

_PACKAGE_DEFAULT_YAML_PATH = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"


def _resolve_backend(solver_config: SolverConfig) -> SolverBackend:
    """Lazily imports ``solvers.highs`` only when actually requested: ``highspy`` is an optional
    extra (``pyproject.toml``'s ``highs`` extra), not a hard dependency of ``inventory_optimizer``
    itself. An eager module-level import here would force that extra onto anyone who imports this
    package at all, breaking ``ARC-003``'s "independently installable" guarantee."""
    if solver_config.backend == "highs":
        try:
            from inventory_optimizer.solvers.highs import HighsBackend
        except ImportError as exc:
            raise ConfigurationError(
                "solver backend 'highs' requires the 'highs' extra (pip install -e '.[highs]')"
            ) from exc
        return HighsBackend()
    raise ConfigurationError(f"unregistered solver backend: {solver_config.backend!r}")


def _solver_options_from_config(solver_config: SolverConfig) -> SolverOptions:
    return SolverOptions(
        time_limit_seconds=solver_config.time_limit_seconds,
        relative_gap=solver_config.relative_gap,
        threads=solver_config.threads,
        seed=solver_config.seed,
        log_level=solver_config.log_level,
    )


def _hash_request(request: OptimizationRequest) -> str:
    """Reuses ``config.hashing.canonical_json`` exactly as ``config.hashing.config_hash`` already
    does for config -- one hashing helper, two callers, no second hash implementation."""
    payload = request.model_dump(mode="json")
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _generate_run_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class InventoryOptimizer:
    """Satisfies ``services.OptimizationService`` structurally (no explicit subclassing needed)."""

    def __init__(
        self, *, config: InventoryOptimizerConfig, backend: SolverBackend | None = None
    ) -> None:
        self._config = config
        self._backend = backend if backend is not None else _resolve_backend(config.solver)
        self._config_hash = config_hash(config)

    @property
    def config(self) -> InventoryOptimizerConfig:
        return self._config

    def optimize(
        self,
        request: OptimizationRequest,
        *,
        platform: PlatformInvocationContext | None = None,
    ) -> OptimizationResult:
        raise_if_invalid(request, max_staleness_hours=self._config.validation.max_staleness_hours)
        context = build_context(request, self._config)
        problem = compile_lp(request, self._config)
        result = self._backend.solve(problem, _solver_options_from_config(self._config.solver))
        verification = verify_solution(problem, result)
        solution = VerifiedSolution(
            context=context, problem=problem, result=result, verification=verification
        )
        return build_optimization_result(
            solution,
            run_id=_generate_run_id(self._config.observability.run_id_prefix),
            created_at=datetime.now(UTC),
            config_hash=self._config_hash,
            input_hash=_hash_request(request),
            platform=platform,
        )


def load_config(
    *, config_path: Path | None = None, overrides: Mapping[str, Any] | None = None
) -> InventoryOptimizerConfig:
    """Deliberately reduced vs. Section 17.1's illustrative five-axis signature -- see
    ``specs/0003-public-api-cli/spec.md``'s Non-Goals and Open Questions. Always applies
    ``configs/default.yaml`` as the ``defaults`` layer; ``config_path`` (if given) is merged as the
    ``run`` layer; ``overrides`` (if given) as the ``overrides`` layer -- both already-named slots
    in ``config.loader.LAYER_ORDER``."""
    defaults = load_yaml_file(_PACKAGE_DEFAULT_YAML_PATH)
    run_layer = load_yaml_file(config_path) if config_path is not None else None
    return build_config(defaults=defaults, run=run_layer, overrides=overrides)
