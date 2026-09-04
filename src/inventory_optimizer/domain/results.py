"""``OptimizationResult`` skeleton.

Section 18.1 of ``01_SPEC.md`` defines fifteen required sections (Identity, Status, Allocations,
Balances, Economics, Demand, Schedules, Collateral, Desk, Sources, Constraints, Solver,
Verification, Warnings, Platform). Phase 0A implements only Identity and Status so the
problem-family registry (T05/T35) has a concrete ``result_type`` to declare; the solver-derived
sections are added by T09-T11 once a backend and verifier exist.
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict

from inventory_optimizer.domain.enums import SolverStatus


class OptimizationResult(BaseModel):
    """Frozen boundary contract. Identity and Status sections only; see module docstring."""

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
