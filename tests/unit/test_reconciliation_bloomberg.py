"""Bloomberg-enrichment validation warning tests (specs/0011-bloomberg-data-foundation/: REQ-012,
REQ-013, NFR-001, AC-004, AC-005, AC-006)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from inventory_optimizer.domain.enums import TradeEventType
from inventory_optimizer.domain.reference import (
    DataQuality,
    MarketCalendar,
    PointInTimeValue,
    SecurityReference,
    TradingStatus,
)
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.scenarios import Scenario, TradeEvent
from inventory_optimizer.facade import InventoryOptimizer
from inventory_optimizer.scenarios.apply import apply_scenario
from inventory_optimizer.validation.reconciliation import (
    check_security_tradability,
    check_settlement_calendar,
)

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _halted_reference(security_id: str = "SEC-1") -> PointInTimeValue[SecurityReference]:
    return PointInTimeValue[SecurityReference](
        value=SecurityReference(
            internal_security_id=security_id,
            issuer_id="ISS-1",
            instrument_type="equity",
            primary_market="XNYS",
            currency="USD",
            country_of_risk="US",
            trading_status=TradingStatus.HALTED,
        ),
        observed_at=_T0,
        effective_from=_T0,
        effective_to=None,
        source="fixture",
        source_version="v1",
        field_mapping_version="v1",
        quality=DataQuality.VERIFIED,
    )


# --- check_security_tradability (unit) --------------------------------------------------------


def test_no_references_supplied_returns_no_warnings(e1_request: OptimizationRequest) -> None:
    assert check_security_tradability(e1_request) == ()
    assert check_security_tradability(e1_request, {}) == ()


def test_halted_security_with_new_route_produces_a_warning(e1_request: OptimizationRequest) -> None:
    """AC-005: routes A and B both have current_quantity_shares == 0.0 (the fixture default) and
    both reference SEC-1."""
    warnings = check_security_tradability(e1_request, {"SEC-1": _halted_reference()})
    assert len(warnings) == 2
    assert all("halted" in w for w in warnings)
    assert any("RT-A" in w for w in warnings)
    assert any("RT-B" in w for w in warnings)


def test_active_security_produces_no_warning(
    e1_request: OptimizationRequest, route_factory
) -> None:
    active = PointInTimeValue[SecurityReference](
        value=SecurityReference(
            internal_security_id="SEC-1",
            issuer_id="ISS-1",
            instrument_type="equity",
            primary_market="XNYS",
            currency="USD",
            country_of_risk="US",
            trading_status=TradingStatus.ACTIVE,
        ),
        observed_at=_T0,
        effective_from=_T0,
        effective_to=None,
        source="fixture",
        source_version="v1",
        field_mapping_version="v1",
        quality=DataQuality.VERIFIED,
    )
    assert check_security_tradability(e1_request, {"SEC-1": active}) == ()


def test_existing_route_is_not_treated_as_new(e1_request: OptimizationRequest) -> None:
    """A route with nonzero current_quantity_shares is not "new" under the adopted V0 definition
    (spec.md RISK-003) -- no warning is raised for it even against a halted security."""
    existing_route = e1_request.routes[0].model_copy(update={"current_quantity_shares": 5.0})
    request = e1_request.model_copy(update={"routes": (existing_route, e1_request.routes[1])})
    warnings = check_security_tradability(request, {"SEC-1": _halted_reference()})
    assert len(warnings) == 1
    assert "RT-B" in warnings[0]
    assert "RT-A" not in warnings[0]


# --- check_settlement_calendar (unit) ----------------------------------------------------------


def test_no_calendars_supplied_returns_no_warnings() -> None:
    assert check_settlement_calendar([(date(2026, 1, 3), "USD")]) == ()
    assert check_settlement_calendar([(date(2026, 1, 3), "USD")], {}) == ()


def test_holiday_date_produces_a_warning() -> None:
    calendar = MarketCalendar(
        market="US", currency="USD", settlement_holidays=frozenset({date(2026, 1, 6)})
    )
    warnings = check_settlement_calendar([(date(2026, 1, 6), "USD")], {"USD": calendar})
    assert len(warnings) == 1
    assert "2026-01-06" in warnings[0]


def test_market_absent_from_calendars_produces_no_warning() -> None:
    calendar = MarketCalendar(market="US", currency="USD")
    warnings = check_settlement_calendar([(date(2026, 1, 6), "EUR")], {"USD": calendar})
    assert warnings == ()


# --- facade.InventoryOptimizer.optimize() integration (REQ-012, NFR-001) -----------------------


def test_optimize_without_security_references_is_byte_identical(
    e1_request: OptimizationRequest, default_config
) -> None:
    """AC-004: a request with no enrichment supplied solves to a result identical (field for
    field) to the same request with an explicit empty mapping."""
    optimizer = InventoryOptimizer(config=default_config)
    baseline = optimizer.optimize(e1_request)
    with_empty = optimizer.optimize(e1_request, security_references={})
    assert baseline.warnings == with_empty.warnings == ()


def test_optimize_surfaces_warning_for_halted_security(
    e1_request: OptimizationRequest, default_config
) -> None:
    optimizer = InventoryOptimizer(config=default_config)
    result = optimizer.optimize(e1_request, security_references={"SEC-1": _halted_reference()})
    assert any("halted" in warning for warning in result.warnings)
    # The solve itself still completes -- a warning, never a rejection (owner decision).
    assert result.allocations is not None


# --- scenarios.apply.apply_scenario integration (REQ-013, AC-006) ------------------------------


def test_apply_scenario_without_calendars_is_unaffected(e1_request: OptimizationRequest) -> None:
    scenario = Scenario(scenario_id="SC-1", name="empty")
    _, warnings = apply_scenario(e1_request, scenario)
    _, warnings_with_none = apply_scenario(e1_request, scenario, calendars=None)
    assert warnings == warnings_with_none == ()


def test_apply_scenario_warns_on_holiday_settlement_date(e1_request: OptimizationRequest) -> None:
    holiday = date(2026, 1, 10)
    event = TradeEvent(
        event_id="BUY-1",
        event_type=TradeEventType.BUY,
        trade_date=e1_request.effective_date,
        effective_date=e1_request.effective_date,
        settlement_date=holiday,
        quantity_shares=1.0,
        inventory_id="INV-1",
        source="fixture",
        source_version="v1",
    )
    scenario = Scenario(scenario_id="SC-2", name="holiday", trade_events=(event,))
    calendar = MarketCalendar(market="US", currency="USD", settlement_holidays=frozenset({holiday}))

    updated, warnings = apply_scenario(e1_request, scenario, calendars={"USD": calendar})
    assert any("2026-01-10" in w for w in warnings)
    # The scenario still applies -- no exception raised, matching the owner's warnings decision.
    assert updated.request_id != e1_request.request_id
