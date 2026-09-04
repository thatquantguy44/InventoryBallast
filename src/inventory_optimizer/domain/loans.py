"""``LoanRoute``: existing or candidate allocation path with economics, eligibility, and limits.

Section 9.3 of ``01_SPEC.md``. Cross-record invariants (demand-group consistency, agreement with
source inventory, on-loan reconciliation) live in ``validation.reconciliation`` because they need
sibling records from the same ``OptimizationRequest``.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoanRoute(BaseModel):
    """Frozen boundary contract. See Section 9.3 for the full field table."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    route_id: str
    inventory_id: str
    security_id: str
    borrower_id: str
    demand_group_id: str
    current_quantity_shares: float = Field(ge=0.0, allow_inf_nan=False)
    hard_minimum_quantity_shares: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    minimum_active_quantity_shares: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    maximum_quantity_shares: float = Field(ge=0.0, allow_inf_nan=False)
    fee_rate: float = Field(allow_inf_nan=False)
    revenue_share: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    reinvestment_rate: float | None = Field(default=None, allow_inf_nan=False)
    collateral_factor: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    variable_cost_rate: float = Field(ge=0.0, allow_inf_nan=False)
    increase_cost_usd_per_share: float = Field(ge=0.0, allow_inf_nan=False)
    decrease_cost_usd_per_share: float = Field(ge=0.0, allow_inf_nan=False)
    recall_notice_days: int = Field(ge=0)
    term_end_date: date | None = None
    eligible: bool
    all_or_none: bool = False
    lot_size_shares: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    priority_class: str | None = None

    @model_validator(mode="after")
    def _check_quantity_bounds(self) -> LoanRoute:
        if self.maximum_quantity_shares < self.hard_minimum_quantity_shares:
            raise ValueError(
                "maximum_quantity_shares must be >= hard_minimum_quantity_shares "
                f"({self.maximum_quantity_shares!r} < {self.hard_minimum_quantity_shares!r})"
            )
        if self.current_quantity_shares > self.maximum_quantity_shares:
            raise ValueError(
                "current_quantity_shares must not exceed maximum_quantity_shares "
                f"({self.current_quantity_shares!r} > {self.maximum_quantity_shares!r})"
            )
        if (
            self.minimum_active_quantity_shares is not None
            and self.minimum_active_quantity_shares > self.maximum_quantity_shares
        ):
            raise ValueError(
                "minimum_active_quantity_shares must not exceed maximum_quantity_shares"
            )
        return self
