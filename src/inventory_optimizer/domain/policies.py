"""Policy and limit contracts: ``CounterpartyLimit`` and ``UtilizationPolicy``.

Section 9.5 of ``01_SPEC.md``.
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class CounterpartyLimit(BaseModel):
    """Borrower gross/notional/name-level limit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    limit_id: str
    borrower_id: str
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None = None
    security_id: str | None = None
    inventory_pool_id: str | None = None
    maximum_notional_usd: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    maximum_quantity_shares: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    hard: bool = True
    risk_class: str | None = None
    source: str
    source_version: str

    @model_validator(mode="after")
    def _check_has_a_bound(self) -> CounterpartyLimit:
        if self.maximum_notional_usd is None and self.maximum_quantity_shares is None:
            raise ValueError(
                "CounterpartyLimit requires maximum_notional_usd, maximum_quantity_shares, or both"
            )
        if (
            self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("effective_to must not precede effective_from")
        return self


class UtilizationPolicy(BaseModel):
    """Floor, target, cap, reserve, cardinality, and soft/hard semantics for one pool/security
    scope. ``maximum_active_routes`` (Section 14.1, T15) is MIP-only -- present, it forces
    ``formulation.lp.compile_lp`` to reject the request in favor of ``formulation.mip.compile_mip``
    (see ``formulation.compiler_support.needs_mip``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: str
    inventory_pool_id: str | None = None
    security_id: str | None = None
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None = None
    minimum_utilization: float | None = Field(default=None, ge=0.0, le=1.0)
    target_utilization: float | None = Field(default=None, ge=0.0, le=1.0)
    maximum_utilization: float | None = Field(default=None, ge=0.0, le=1.0)
    reserve_buffer_shares: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    reserve_buffer_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    target_hard: bool = False
    target_penalty_usd_per_share: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    target_priority: int | None = None
    maximum_active_routes: int | None = Field(default=None, ge=0)
    source: str
    source_version: str

    @model_validator(mode="after")
    def _check_ordering_and_soft_terms(self) -> UtilizationPolicy:
        bounds = [
            b
            for b in (self.minimum_utilization, self.target_utilization, self.maximum_utilization)
            if b is not None
        ]
        if bounds != sorted(bounds):
            raise ValueError(
                "minimum_utilization <= target_utilization <= maximum_utilization is required "
                f"where present; got min={self.minimum_utilization!r}, "
                f"target={self.target_utilization!r}, max={self.maximum_utilization!r}"
            )
        if (
            self.target_utilization is not None
            and not self.target_hard
            and self.target_penalty_usd_per_share is None
        ):
            raise ValueError(
                "a soft target_utilization requires an explicit target_penalty_usd_per_share"
            )
        if (
            self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("effective_to must not precede effective_from")
        return self
