"""Point-in-time reference data contracts (specs/0011-bloomberg-data-foundation/; Section 22.3).

``PointInTimeValue[T]`` is the one envelope every enriched value in this workstream is wrapped in;
``SecurityReference`` and ``MarketCalendar`` are the two payload contracts Realism release R0
(T19-T21) needs. ``EntityRelationship`` lands with the R1 entity-hierarchy slice (T22) so borrower
limits can aggregate across approved legal entities without adding a second point-in-time envelope.
Section 22.3's other required contracts (``MarketState``, ``LiquidityEstimate``, ``FundHolding``)
remain R1+ concepts declared alongside their consuming slices.

Every value carries its own knowledge/effective time and provenance so
``enrichment.point_in_time.resolve_latest_known`` can answer "what was known, and true, as of when"
without ever looking ahead (NFR-003). Nothing in this module is authoritative over the optimizer's
own internal contracts (``SecurityInventory``, ``LoanRoute``) -- Section 22.1's source-of-truth
table: Bloomberg enriches, it does not override.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class DataQuality(StrEnum):
    """Section 22.1's table: an enriched value's own confidence, not the optimizer's confidence in
    a decision. Kept minimal for R0 -- more values (e.g. ``UNENTITLED``, ``FUTURE_EFFECTIVE``) are
    additive once a real adapter exists to produce them (spec.md's Assumptions)."""

    VERIFIED = "verified"
    ESTIMATED = "estimated"
    STALE = "stale"
    CONFLICTING = "conflicting"


class TradingStatus(StrEnum):
    """Section 22.4's "Tradability and market status" row."""

    ACTIVE = "active"
    HALTED = "halted"
    SUSPENDED = "suspended"
    DELISTED = "delisted"


class PointInTimeValue(BaseModel, Generic[T]):
    """Section 22.3's envelope, verbatim: every enriched value carries when the firm received it
    (``observed_at``), when it applies economically (``effective_from``/``effective_to``), and
    its provenance. ``enrichment.point_in_time.resolve_latest_known`` is the sole place these
    fields are interpreted jointly -- this class only validates internal consistency."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: T
    observed_at: AwareDatetime
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None = None
    source: str
    source_version: str
    field_mapping_version: str
    quality: DataQuality

    @model_validator(mode="after")
    def _check_interval(self) -> PointInTimeValue[T]:
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self


class SecurityReference(BaseModel):
    """Section 22.3's ``SecurityReference`` contract, scoped to what T19-T21 actually consume.
    ``external_identifiers`` is a plain string-keyed mapping (e.g. ``{"FIGI": "..."}``) rather than
    named vendor-specific fields -- deployment-specific identifier schemes vary, and REQ-008
    already forbids a vendor mnemonic from appearing outside ``adapters/bloomberg/``; a generic
    mapping keeps this contract from assuming Bloomberg is the only source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    internal_security_id: str
    external_identifiers: Mapping[str, str] = {}
    issuer_id: str
    share_class: str | None = None
    instrument_type: str
    primary_market: str
    currency: str
    country_of_risk: str
    trading_status: TradingStatus
    settlement_status: str | None = None
    lot_size: float | None = None
    tick_size: float | None = None


class EntityRelationship(BaseModel):
    """Section 22.3/22.9 borrower hierarchy payload.

    Effective dates, observation time, source lineage, and data quality stay on the surrounding
    ``PointInTimeValue`` envelope; this payload only names the hierarchy relationship itself.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str
    legal_entity_id: str
    ultimate_parent_id: str
    relationship_type: str
    ownership_confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


class MarketCalendar(BaseModel):
    """Section 22.3's ``MarketCalendar`` contract, scoped to the settlement-day predicate T21/
    REQ-013/REQ-014 need. ``market`` is a plain deployment-defined identifier -- this repo's own
    callers key by currency today (``plan.md``'s Validation wiring section records this as a
    named simplification, not a silent one)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    market: str
    currency: str
    trading_holidays: frozenset[date] = frozenset()
    settlement_holidays: frozenset[date] = frozenset()
    exceptional_closures: frozenset[date] = frozenset()

    def is_settlement_day(self, day: date) -> bool:
        """Weekday, and not a settlement holiday or an exceptional closure. Trading holidays are
        tracked separately (a market can trade without settling, e.g. around some closures) but are
        not consulted here -- R0 only needs the settlement predicate."""
        return (
            day.weekday() < 5
            and day not in self.settlement_holidays
            and day not in self.exceptional_closures
        )
