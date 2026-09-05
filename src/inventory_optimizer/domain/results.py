"""``OptimizationResult`` and its section contracts (Section 18.1 of ``01_SPEC.md``).

Section 18.1 defines fifteen required sections (Identity, Status, Allocations, Balances,
Economics, Demand, Schedules, Collateral, Desk, Sources, Constraints, Solver, Verification,
Warnings, Platform). Phase 0A implemented only Identity and Status; T11 adds the remaining
thirteen.

This module deliberately imports nothing from ``formulation``, ``validation``, ``reporting``, or
``config`` -- the same "frozen boundary contract, no upward dependency" discipline every other
``domain/*.py`` module already follows. Where a T11 section mirrors a type from an inner layer
(``validation.solution_verifier.VerificationReport``, ``reporting.types.ObjectiveAttribution``,
``formulation.indexes.RowKey``), this module defines its own plain-data equivalent and
``reporting.result_builder`` converts at assembly time, rather than this module reaching upward
for the original type. ``domain.requests.DeskContext`` and
``platform.context.PlatformInvocationContext`` are the two exceptions: both are themselves frozen,
Phase-0A boundary contracts at the same layer
(the former in this same package; the latter importing only ``domain.enums``), so embedding them
directly avoids a needless duplicate mirror.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from inventory_optimizer.domain.enums import ProblemFamily, ReasonCode, SolverStatus
from inventory_optimizer.platform.context import PlatformInvocationContext


class RowIdentifier(BaseModel):
    """Plain-data mirror of ``formulation.indexes.RowKey``: which named row this is, without
    ``domain/`` importing ``formulation/``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    scope_id: str


class AllocationRecord(BaseModel):
    """One route's Section 18.1 "Allocations" row, plus the Section 18.3 explanation for its
    change, if any."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    route_id: str
    inventory_id: str
    demand_group_id: str
    current_quantity_shares: float
    post_quantity_shares: float
    increase_shares: float
    decrease_shares: float
    fee_rate: float
    demand_cap_shares: float | None
    eligible: bool
    reason_codes: tuple[ReasonCode, ...] = ()
    explanation_evidence: Mapping[str, float | str] = Field(
        default_factory=lambda: MappingProxyType({})
    )


class BalanceRecord(BaseModel):
    """One inventory record's Section 18.1 "Balances" row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inventory_id: str
    pre_total_lendable_shares: float
    pre_reserved_shares: float
    pre_committed_out_shares: float
    pre_on_loan_shares: float
    pre_available_to_lend_shares: float
    post_available_shares: float
    post_on_loan_shares: float
    utilization: float


class ObjectiveAttributionRecord(BaseModel):
    """Plain-data mirror of ``reporting.types.ObjectiveAttribution`` (Section 18.2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    component_name: str
    component_version: str
    unscaled_value_usd: float
    baseline_value_usd: float
    delta_usd: float


class EconomicsSummary(BaseModel):
    """Section 18.1 "Economics": every objective component's attributed value, and the totals
    they must reconcile to (VER-002)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    components: tuple[ObjectiveAttributionRecord, ...]
    total_value_usd: float
    total_delta_usd: float


class DemandSummary(BaseModel):
    """One demand group's Section 18.1 "Demand" row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    demand_group_id: str
    reference_quantity_shares: float
    raw_demand_shares: float
    effective_cap_shares: float
    filled_shares: float
    unfilled_shares: float
    fill_ratio: float
    reason_code: ReasonCode | None = None


class DeskSummary(BaseModel):
    """Section 18.1 "Desk": problem family, desk/legal entity, attribution scope, and which
    optional family components ran. Mirrors ``domain.requests.DeskContext`` plus
    ``config.models.DeskConfig.enabled_components`` (read at assembly time, not imported here)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    problem_family: ProblemFamily
    legal_entity_id: str | None
    platform_tenant_id: str | None
    attribution_scope: str | None
    enabled_components: tuple[str, ...]


class ConstraintActivity(BaseModel):
    """One row's Section 18.1 "Constraints" entry: bounds, activity, slack, and its dual when the
    backend supplied one and it passed verification (Section 18.4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    row: RowIdentifier
    lower: float
    upper: float
    activity: float
    slack: float
    dual_value: float | None = None


class SolverDiagnostics(BaseModel):
    """Section 18.1 "Solver": runtime, iteration/node counts, gap/bound, and backend identity.
    Never carries the primal/dual arrays themselves (NFR-002; Section 20.1's "never serialize a
    solver model by default")."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend_name: str
    backend_version: str
    runtime_seconds: float
    iterations: int | None
    nodes: int | None
    best_bound: float | None
    relative_gap: float | None
    termination_reason: str


class VerificationSection(BaseModel):
    """Plain-data mirror of ``validation.solution_verifier.VerificationReport`` (Section 18.1
    "Verification"; VER-001)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    has_primal: bool
    max_variable_bound_violation: float
    max_row_violation: float
    max_integrality_violation: float
    objective_reconstruction_delta: float
    passed: bool


class OptimizationResult(BaseModel):
    """Frozen boundary contract. All fifteen Section 18.1 sections. Sections with no implemented
    upstream domain model yet (Schedules, Collateral, Sources) are explicitly ``None`` -- an
    honest "not produced," not a fabricated empty record (constitution P6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Identity
    request_id: str
    run_id: str
    created_at: AwareDatetime
    config_hash: str
    input_hash: str
    package_version: str
    backend_version: str | None = None

    # Status
    status: SolverStatus
    native_status: str | None = None
    strict: bool = True
    termination_reason: str | None = None

    # Sections 18.1's remaining thirteen (T11)
    allocations: tuple[AllocationRecord, ...]
    balances: tuple[BalanceRecord, ...]
    economics: EconomicsSummary
    demand: tuple[DemandSummary, ...]
    schedules: None = None
    collateral: None = None
    desk: DeskSummary | None = None
    sources: None = None
    constraints: tuple[ConstraintActivity, ...]
    solver: SolverDiagnostics
    verification: VerificationSection
    warnings: tuple[str, ...] = ()
    platform: PlatformInvocationContext | None = None
