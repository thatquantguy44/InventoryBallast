"""Validated, frozen configuration objects (Section 8.2 of ``01_SPEC.md``).

Phase 0A implements the sections the E1 vertical uses: ``desk``, ``formulation``, ``validation``,
``solver``, ``observability``. ``objective``, ``constraints``, ``schedules``, ``collateral``,
``elasticity``, and ``scenarios`` are added as those subsystems land; until then, supplying them
is rejected by ``extra="forbid"`` rather than silently ignored.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from inventory_optimizer.domain.enums import DayCountBasis, Formulation, ProblemFamily, QuantityType


class DeskConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    problem_family: ProblemFamily = ProblemFamily.SECURITIES_LENDING_INVENTORY
    enabled_components: tuple[str, ...] = ()


class FormulationConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Formulation = Formulation.LP
    planning_horizon_days: int = Field(default=1, ge=1)
    day_count_basis: DayCountBasis = DayCountBasis.ACT_360
    quantity_type: QuantityType = QuantityType.CONTINUOUS
    scaling: bool = False


class ValidationConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    balance_tolerance_shares: float = Field(default=1e-6, ge=0.0)
    max_staleness_hours: float = Field(default=24.0, ge=0.0)
    duplicate_id_policy: str = "reject"


class SolverConfig(BaseModel):
    """Informational in Phase 0A; no backend is invoked until T09."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: str = "highs"
    time_limit_seconds: float | None = Field(default=None, gt=0.0)
    relative_gap: float | None = Field(default=None, ge=0.0)
    threads: int | None = Field(default=None, ge=1)
    seed: int | None = None
    log_level: str = "warning"


class ObservabilityConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id_prefix: str = "inv-opt"
    audit_enabled: bool = False


class InventoryOptimizerConfig(BaseModel):
    """Section 8.2. Frozen after validation; unknown top-level or nested keys fail closed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    desk: DeskConfig = Field(default_factory=DeskConfig)
    formulation: FormulationConfig = Field(default_factory=FormulationConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    solver: SolverConfig = Field(default_factory=SolverConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
