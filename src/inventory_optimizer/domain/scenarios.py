"""Scenario input contracts (T13-T14; Section 13.1 of ``01_SPEC.md``).

Scoped to what today's domain contracts and worked examples (``EXAMPLES.md`` E2, E3) actually
support: typed trade events (all seven kinds) plus route-level fee shocks and demand-forecast
shocks. ``schedule_overlays``, ``collateral_shocks``, and ``desk_events`` are not declared at all
-- they need subsystems (T29, T30-T32, T35-T39) that do not exist yet; see
``specs/0004-scenario-engine/spec.md``'s Non-Goals.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from inventory_optimizer.domain.enums import TradeEventType

_INVENTORY_EVENT_TYPES = frozenset(
    {
        TradeEventType.BUY,
        TradeEventType.SELL,
        TradeEventType.TRANSFER_IN,
        TradeEventType.TRANSFER_OUT,
    }
)
_ROUTE_EVENT_TYPES = frozenset(
    {TradeEventType.NEW_LOAN, TradeEventType.RETURN, TradeEventType.RECALL}
)


class TradeEvent(BaseModel):
    """Frozen boundary contract. See Section 13.1 for the full field table."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    event_type: TradeEventType
    trade_date: date
    effective_date: date
    settlement_date: date
    quantity_shares: float = Field(gt=0.0, allow_inf_nan=False)
    inventory_id: str | None = None
    route_id: str | None = None
    trade_price_usd: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    source: str
    source_version: str

    @model_validator(mode="after")
    def _check_required_reference(self) -> TradeEvent:
        if self.event_type in _INVENTORY_EVENT_TYPES and self.inventory_id is None:
            raise ValueError(f"{self.event_type} requires inventory_id")
        if self.event_type in _ROUTE_EVENT_TYPES and self.route_id is None:
            raise ValueError(f"{self.event_type} requires route_id")
        return self


class RateShock(BaseModel):
    """A route-level fee override (Section 13.1's ``rate_shocks``, scoped to route fee rate --
    see spec.md's Non-Goals)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shock_id: str
    route_id: str
    new_fee_rate: float = Field(allow_inf_nan=False)
    source: str
    source_version: str


class DemandShock(BaseModel):
    """A demand-forecast override (Section 13.1's ``demand_shocks``, scoped to
    ``DemandForecast``'s own fields)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shock_id: str
    demand_group_id: str
    reference_quantity_shares: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    reference_fee_rate: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    elasticity: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    hard_max_quantity_shares: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    source: str
    source_version: str

    @model_validator(mode="after")
    def _check_has_an_override(self) -> DemandShock:
        overrides = (
            self.reference_quantity_shares,
            self.reference_fee_rate,
            self.elasticity,
            self.hard_max_quantity_shares,
        )
        if all(value is None for value in overrides):
            raise ValueError("DemandShock requires at least one override field")
        return self


class Scenario(BaseModel):
    """Frozen boundary contract. Scoped subset of Section 13.1's full model -- see spec.md's
    Non-Goals for ``schedule_overlays``/``collateral_shocks``/``desk_events``/``inventory_shocks``/
    ``policy_overrides``, none of which are declared here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: str
    name: str
    trade_events: tuple[TradeEvent, ...] = ()
    rate_shocks: tuple[RateShock, ...] = ()
    demand_shocks: tuple[DemandShock, ...] = ()
    metadata: Mapping[str, str] = Field(default_factory=lambda: MappingProxyType({}))

    @field_serializer("metadata")
    def _serialize_metadata(self, value: Mapping[str, str]) -> dict[str, str]:
        return dict(value)

    @model_validator(mode="after")
    def _check_unique_event_ids(self) -> Scenario:
        event_ids = [event.event_id for event in self.trade_events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("trade_events event_id values must be unique within a scenario")
        return self
