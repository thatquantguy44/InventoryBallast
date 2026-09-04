"""``SecurityInventory``: one pool/security supply record and its baseline reconciliation.

Section 9.2 of ``01_SPEC.md``. Section 5.1 defines the canonical balance identity:

    available_to_lend = total_lendable - on_loan - reserved - committed_out

``total_lendable`` includes shares already on loan. Upstream feeds that use ``lendable_supply`` to
mean only available supply must be mapped explicitly by the adapter before reaching this contract;
this class never guesses the convention.
"""

from __future__ import annotations

from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

BALANCE_TOLERANCE_SHARES = 1e-6


class SecurityInventory(BaseModel):
    """Frozen boundary contract. See Section 9.2 for the full field table."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inventory_id: str
    inventory_pool_id: str
    security_id: str
    as_of: AwareDatetime
    settlement_date: date
    total_lendable_shares: float = Field(ge=0.0)
    on_loan_shares: float = Field(ge=0.0)
    reserved_shares: float = Field(ge=0.0)
    committed_out_shares: float = Field(ge=0.0)
    available_to_lend_shares: float = Field(ge=0.0)
    price_usd: float = Field(gt=0.0)
    currency: str
    eligible: bool
    source_version: str

    @model_validator(mode="after")
    def _check_balance_identity(self) -> SecurityInventory:
        expected = (
            self.total_lendable_shares
            - self.on_loan_shares
            - self.reserved_shares
            - self.committed_out_shares
        )
        if abs(expected - self.available_to_lend_shares) > BALANCE_TOLERANCE_SHARES:
            raise ValueError(
                "available_to_lend_shares must equal total_lendable_shares - on_loan_shares - "
                f"reserved_shares - committed_out_shares (expected {expected!r}, "
                f"got {self.available_to_lend_shares!r})"
            )
        if self.on_loan_shares > self.total_lendable_shares + BALANCE_TOLERANCE_SHARES:
            raise ValueError("on_loan_shares cannot exceed total_lendable_shares")
        return self

    @model_validator(mode="after")
    def _check_currency(self) -> SecurityInventory:
        if self.currency != "USD":
            raise ValueError(
                f"currency must be USD in core V0; got {self.currency!r}. Convert upstream via "
                "an adapter before constructing SecurityInventory."
            )
        return self
