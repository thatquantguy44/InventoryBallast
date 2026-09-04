"""``DemandForecast``: demand-group reference quantity/rate, elasticity, uncertainty, and caps.

Section 9.4 of ``01_SPEC.md``.
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


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

    @model_validator(mode="after")
    def _check_reference_fee_rate_when_elastic(self) -> DemandForecast:
        if self.elasticity > 0.0 and self.reference_fee_rate <= 0.0:
            raise ValueError(
                "reference_fee_rate must be strictly positive when elasticity is used "
                f"(elasticity={self.elasticity!r})"
            )
        return self
