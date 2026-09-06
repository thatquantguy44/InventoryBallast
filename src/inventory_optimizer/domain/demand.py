"""``DemandForecast``: demand-group reference quantity/rate, elasticity, uncertainty, and caps.

Section 9.4 of ``01_SPEC.md``. ``candidate_fee_rates`` (specs/0009-discrete-fee-tier-pricing/) is
an optional, empty-by-default menu of candidate borrower fees for Section 12.4's discrete
price-selection MIP -- absent, a forecast behaves exactly as it always has.
"""

from __future__ import annotations

import math

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

_MAX_CANDIDATE_FEE_TIERS = 1000


class DemandForecast(BaseModel):
    """Frozen boundary contract. See Section 9.4 for the full field table."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    demand_group_id: str
    security_id: str
    borrower_id: str
    as_of: AwareDatetime
    reference_quantity_shares: float = Field(ge=0.0, allow_inf_nan=False)
    reference_fee_rate: float = Field(ge=0.0, allow_inf_nan=False)
    elasticity: float = Field(ge=0.0, allow_inf_nan=False)
    forecast_std_shares: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    hard_max_quantity_shares: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    source_model: str
    source_version: str
    candidate_fee_rates: tuple[float, ...] = ()

    @model_validator(mode="after")
    def _check_reference_fee_rate_when_elastic(self) -> DemandForecast:
        if self.elasticity > 0.0 and self.reference_fee_rate <= 0.0:
            raise ValueError(
                "reference_fee_rate must be strictly positive when elasticity is used "
                f"(elasticity={self.elasticity!r})"
            )
        return self

    @model_validator(mode="after")
    def _check_candidate_fee_rates(self) -> DemandForecast:
        fees = self.candidate_fee_rates
        if len(fees) > _MAX_CANDIDATE_FEE_TIERS:
            raise ValueError(
                f"candidate_fee_rates supports at most {_MAX_CANDIDATE_FEE_TIERS} candidate "
                f"tiers per demand group (got {len(fees)}) -- the zero-padded tier variable-key "
                "index only spans that range"
            )
        for fee in fees:
            if not math.isfinite(fee) or fee <= 0.0:
                raise ValueError(
                    f"candidate_fee_rates must be strictly positive and finite (got {fee!r})"
                )
        for previous, current in zip(fees, fees[1:]):
            if current <= previous:
                raise ValueError(
                    "candidate_fee_rates must be strictly increasing and free of duplicates "
                    f"(got {fees!r})"
                )
        return self
