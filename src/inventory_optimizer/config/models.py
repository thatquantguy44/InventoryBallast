"""Validated, frozen configuration objects (Section 8.2 of ``01_SPEC.md``).

Phase 0A implements the sections the E1/E2 vertical uses: ``desk``, ``formulation``,
``validation``, ``solver``, ``observability``, ``elasticity``. ``objective`` is added by T18
(Phase 4 QP; see ``ObjectiveConfig`` below). ``constraints``, ``schedules``, ``collateral``, and
``scenarios`` are still added as those subsystems land; until then, supplying them is rejected by
``extra="forbid"`` rather than silently ignored.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from inventory_optimizer.domain.enums import (
    DayCountBasis,
    ElasticityCurveType,
    Formulation,
    ProblemFamily,
    QuantityType,
)


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


class ElasticityConfig(BaseModel):
    """Section 8.2: "curve type, floors/caps, missing-estimate policy, uncertainty haircut."

    ``missing_elasticity`` policy (Section 12.3) is not modeled here: ``DemandForecast.elasticity``
    is a required field, so resolving a *missing* upstream estimate is an ingestion/adapter concern
    that happens before a ``DemandForecast`` exists, not something this core config controls.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    curve: ElasticityCurveType = ElasticityCurveType.CONSTANT
    fee_floor: float = Field(default=1e-6, gt=0.0)
    uncertainty_haircut_sigma: float = Field(default=1.0, ge=0.0)


class ObjectiveConfig(BaseModel):
    """Section 8.2's deferred ``objective`` section starts landing here (T18; Section 14.2).

    ``allocation_stability_penalty`` is Phase 4's one convex QP term: a desk-level coefficient
    (USD per share-squared) penalizing route quantity deviation from the current book, uniformly
    across every route -- a desk policy decision, not a per-route/per-request field (unlike
    Phase 3's MIP triggers). Zero (the default) means "no penalty configured":
    ``formulation.compiler_support.needs_qp`` never triggers, so a config predating this field
    behaves identically.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    allocation_stability_penalty: float = Field(default=0.0, ge=0.0)


class MultiPeriodConfig(BaseModel):
    """specs/0010-multi-period-settlement/: the per-day discount rate applied to both the
    deterministic projection's and the joint multi-period LP's per-period economics. Zero (the
    default) means "no discounting configured" -- a config predating this field behaves
    identically, the same zero-default convention ``ObjectiveConfig.allocation_stability_penalty``
    already established."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    daily_discount_rate: float = Field(default=0.0, ge=0.0)


class InventoryOptimizerConfig(BaseModel):
    """Section 8.2. Frozen after validation; unknown top-level or nested keys fail closed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    desk: DeskConfig = Field(default_factory=DeskConfig)
    formulation: FormulationConfig = Field(default_factory=FormulationConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    solver: SolverConfig = Field(default_factory=SolverConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    elasticity: ElasticityConfig = Field(default_factory=ElasticityConfig)
    objective: ObjectiveConfig = Field(default_factory=ObjectiveConfig)
    multi_period: MultiPeriodConfig = Field(default_factory=MultiPeriodConfig)
