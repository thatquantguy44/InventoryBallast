"""Expected-economics input contracts (specs/0012-expected-economics-realism/).

These records are optimizer inputs with lineage. Nothing in this package estimates, trains, or
calibrates the values; upstream model governance owns those processes.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ExpectedEconomics(BaseModel):
    """Per-route expected-economics coefficients from Section 22.5.

    ``model_version``/``calibration_date``/``uncertainty`` describe the supplied estimate record as
    a whole. The optimizer consumes the values; it does not infer them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    route_id: str
    take_up_probability: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    conditional_expected_days_active: float = Field(gt=0.0, allow_inf_nan=False)
    return_hazard: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    repricing_hazard: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    recall_failure_probability: float | None = Field(
        default=None, ge=0.0, le=1.0, allow_inf_nan=False
    )
    manufactured_payment_cost_usd: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    indemnification_capital_cost_usd: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    settlement_fail_cost_usd: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    relationship_value_or_cost_usd: float = Field(default=0.0, allow_inf_nan=False)
    model_version: str
    calibration_date: date
    uncertainty: float = Field(ge=0.0, allow_inf_nan=False)
