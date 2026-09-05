"""``OptimizationRequest``: complete baseline solve request, and its ``DeskContext``.

Section 9.7 of ``01_SPEC.md``. This Phase 0A version carries the core fields every problem family
uses (inventory, routes, demand, counterparty/utilization policy) plus the platform-facing
identity fields. Schedule tuples (``eligibility_schedules``, ``collateral_schedules``,
``constraint_schedules``) and agency/prime tuples (``beneficial_owner_mandates``,
``inventory_sources``, ``client_short_demands``, ``external_borrow_quotes``,
``indemnification_policies``, ``agreement_netting_sets``, ``balance_sheet_budgets``) are additive
fields introduced alongside their owning subsystems (T29-T33, T35-T39); adding them is not expected
to change the fields defined here.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_serializer

from inventory_optimizer.domain.demand import DemandForecast
from inventory_optimizer.domain.enums import ProblemFamily
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.policies import CounterpartyLimit, UtilizationPolicy


class DeskContext(BaseModel):
    """Selected problem family, desk/legal entity, platform tenant, and attribution scope.

    The full contract (owner mandates, source hierarchy, capability requirements) lands with the
    desk-profile registry (T35) and agency/prime workstreams (T36-T39); this is the Phase 0A
    subset needed to route a request to the correct problem family.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    problem_family: ProblemFamily = ProblemFamily.SECURITIES_LENDING_INVENTORY
    legal_entity_id: str | None = None
    platform_tenant_id: str | None = None
    attribution_scope: str | None = None


class OptimizationRequest(BaseModel):
    """Frozen boundary contract. See Section 9.7 for the full (target) field table."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    as_of: AwareDatetime
    effective_date: date
    problem_family: ProblemFamily = ProblemFamily.SECURITIES_LENDING_INVENTORY
    desk_context: DeskContext | None = None
    inventory: tuple[SecurityInventory, ...]
    routes: tuple[LoanRoute, ...]
    demand: tuple[DemandForecast, ...]
    counterparty_limits: tuple[CounterpartyLimit, ...] = ()
    utilization_policies: tuple[UtilizationPolicy, ...] = ()
    config_overrides: Mapping[str, JsonValue] = Field(default_factory=lambda: MappingProxyType({}))
    metadata: Mapping[str, str] = Field(default_factory=lambda: MappingProxyType({}))

    @field_serializer("config_overrides", "metadata")
    def _serialize_immutable_mapping(self, value: Mapping[str, object]) -> dict[str, object]:
        """``MappingProxyType`` (this class's own default) has no pydantic-core serializer --
        ``model_dump``/``model_dump_json`` raise ``PydanticSerializationError`` on it otherwise.
        Converting to a plain ``dict`` only at the serialization boundary keeps the in-memory
        immutability guarantee the default was chosen for."""
        return dict(value)
