"""``reporting.tables`` tests (specs/0008-tabular-result-output/spec.md AC-001, AC-002, AC-003,
AC-011): table names/order, exact column contracts, one row per source record, enum/tuple/mapping
normalization, and both run-summary layouts.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from inventory_optimizer.facade import InventoryOptimizer
from inventory_optimizer.reporting.result_builder import build_optimization_result
from inventory_optimizer.reporting.tables import (
    RunSummaryLayout,
    Table,
    result_tables,
    run_summary_long_table,
    run_summary_table,
    scenario_tables,
    stress_tables,
)
from inventory_optimizer.reporting.types import VerifiedSolution
from inventory_optimizer.scenarios.runner import run_scenarios, run_stress_test


@pytest.fixture
def e1_result(e1_solution: VerifiedSolution):
    return build_optimization_result(
        e1_solution,
        run_id="run-tables-test",
        created_at=datetime(2026, 9, 3, tzinfo=UTC),
        config_hash="cfg-hash-test",
        input_hash="input-hash-test",
    )


def test_result_tables_names_and_order(e1_result) -> None:
    """AC-001."""
    tables = result_tables(e1_result)
    assert [t.name for t in tables] == [
        "allocations",
        "allocation_evidence",
        "balances",
        "demand",
        "constraints",
        "economics",
        "run_summary",
    ]
    assert all(isinstance(t, Table) for t in tables)


def test_allocations_columns_match_contract(e1_result) -> None:
    """AC-001."""
    table = result_tables(e1_result)[0]
    assert table.columns == (
        "route_id",
        "inventory_id",
        "demand_group_id",
        "current_quantity_shares",
        "post_quantity_shares",
        "increase_shares",
        "decrease_shares",
        "fee_rate",
        "demand_cap_shares",
        "eligible",
        "reason_codes",
    )


def test_allocations_row_per_record(e1_result) -> None:
    """AC-001: one row per AllocationRecord with values equal to that record's own fields."""
    table = result_tables(e1_result)[0]
    assert len(table.rows) == len(e1_result.allocations)
    by_route = {row[0]: row for row in table.rows}
    for allocation in e1_result.allocations:
        row = by_route[allocation.route_id]
        assert row[1] == allocation.inventory_id
        assert row[2] == allocation.demand_group_id
        assert row[3] == allocation.current_quantity_shares
        assert row[4] == allocation.post_quantity_shares
        assert row[7] == allocation.fee_rate
        assert row[9] == allocation.eligible


def test_reason_codes_joined_on_allocations(e1_result) -> None:
    """AC-002."""
    table = result_tables(e1_result)[0]
    reason_column = table.columns.index("reason_codes")
    for allocation, row in zip(e1_result.allocations, table.rows, strict=True):
        if allocation.reason_codes:
            assert row[reason_column] == "|".join(c.value for c in allocation.reason_codes)
        else:
            assert row[reason_column] == ""


def test_evidence_emitted_long_format_sorted(e1_result) -> None:
    """AC-002: explanation_evidence is a long route_id/key/value table, keys sorted per route so
    output is byte-stable."""
    table = result_tables(e1_result)[1]
    assert table.name == "allocation_evidence"
    assert table.columns == ("route_id", "key", "value")

    expected_rows = 0
    for allocation in e1_result.allocations:
        keys = sorted(allocation.explanation_evidence)
        expected_rows += len(keys)
        route_rows = [row for row in table.rows if row[0] == allocation.route_id]
        assert [row[1] for row in route_rows] == keys
        for key, row in zip(keys, route_rows, strict=True):
            assert row[2] == str(allocation.explanation_evidence[key])
    assert len(table.rows) == expected_rows


def test_balances_and_demand_row_counts(e1_result) -> None:
    tables = result_tables(e1_result)
    balances, demand = tables[2], tables[3]
    assert len(balances.rows) == len(e1_result.balances)
    assert len(demand.rows) == len(e1_result.demand)
    assert balances.columns[0] == "inventory_id"
    assert demand.columns[0] == "demand_group_id"


def test_constraints_row_per_activity(e1_result) -> None:
    table = result_tables(e1_result)[4]
    assert table.columns == (
        "row_kind",
        "row_scope_id",
        "lower",
        "upper",
        "activity",
        "slack",
        "dual_value",
    )
    assert len(table.rows) == len(e1_result.constraints)
    for activity, row in zip(e1_result.constraints, table.rows, strict=True):
        assert row[0] == activity.row.kind
        assert row[1] == activity.row.scope_id
        assert row[2] == activity.lower
        assert row[3] == activity.upper


def test_economics_row_per_component(e1_result) -> None:
    table = result_tables(e1_result)[5]
    assert len(table.rows) == len(e1_result.economics.components)
    for component, row in zip(e1_result.economics.components, table.rows, strict=True):
        assert row[0] == component.component_name
        assert row[2] == component.unscaled_value_usd
        assert row[4] == component.delta_usd


def test_run_summary_wide_is_single_row(e1_result) -> None:
    """AC-011."""
    table = run_summary_table(e1_result)
    assert len(table.rows) == 1
    row = table.rows[0]
    assert row[table.columns.index("request_id")] == e1_result.request_id
    assert row[table.columns.index("run_id")] == e1_result.run_id
    assert row[table.columns.index("status")] == e1_result.status.value
    assert row[table.columns.index("objective_total_value_usd")] == pytest.approx(
        e1_result.economics.total_value_usd
    )
    assert row[table.columns.index("verification_passed")] == e1_result.verification.passed


def test_run_summary_desk_none_keeps_fixed_width(e1_result) -> None:
    """desk is optional; its four columns are None when absent, and the row's width never
    varies."""
    without_desk = e1_result.model_copy(update={"desk": None})
    table = run_summary_table(without_desk)
    assert len(table.rows[0]) == len(table.columns)
    assert table.rows[0][table.columns.index("desk_problem_family")] is None


def test_run_summary_long_matches_wide_keys_and_values(e1_result) -> None:
    """AC-011: long is derived from wide, so the two cannot drift -- same keys, same order, same
    values, every row's run_id equal to the result's own run_id."""
    wide = run_summary_table(e1_result)
    long = run_summary_long_table(e1_result)

    assert long.name == "run_summary_long"
    assert long.columns == ("run_id", "key", "value")
    assert len(long.rows) == len(wide.columns)
    assert [row[1] for row in long.rows] == list(wide.columns)
    assert [row[2] for row in long.rows] == list(wide.rows[0])
    assert all(row[0] == e1_result.run_id for row in long.rows)


def test_result_tables_uses_long_run_summary_when_requested(e1_result) -> None:
    tables = result_tables(e1_result, run_summary_layout=RunSummaryLayout.LONG)
    assert tables[-1].name == "run_summary_long"


def test_scenario_tables_row_per_delta(e1_request, default_config) -> None:
    """AC-003."""
    optimizer = InventoryOptimizer(config=default_config)
    baseline = optimizer.optimize(e1_request)
    from inventory_optimizer.domain.scenarios import RateShock, Scenario

    scenario = Scenario(
        scenario_id="RATE-UP",
        name="RATE-UP",
        rate_shocks=(
            RateShock(
                shock_id="RATE-UP-1",
                route_id="RT-A",
                new_fee_rate=0.05,
                source="fixture",
                source_version="v1",
            ),
        ),
    )
    comparisons = run_scenarios(e1_request, baseline, [scenario], optimizer)

    tables = scenario_tables(comparisons)
    assert [t.name for t in tables] == [
        "scenario_summary",
        "scenario_allocations",
        "scenario_balances",
        "scenario_economics",
    ]
    summary, allocations, balances, economics = tables
    assert len(summary.rows) == 1
    assert len(allocations.rows) == len(comparisons[0].allocations)
    assert len(balances.rows) == len(comparisons[0].balances)
    assert all(row[0] == "RATE-UP" for row in allocations.rows)
    assert all(row[0] == "RATE-UP" for row in economics.rows)


def test_scenario_economics_keys_sorted(e1_request, default_config) -> None:
    optimizer = InventoryOptimizer(config=default_config)
    baseline = optimizer.optimize(e1_request)
    from inventory_optimizer.domain.scenarios import RateShock, Scenario

    scenario = Scenario(
        scenario_id="RATE-UP",
        name="RATE-UP",
        rate_shocks=(
            RateShock(
                shock_id="RATE-UP-1",
                route_id="RT-A",
                new_fee_rate=0.05,
                source="fixture",
                source_version="v1",
            ),
        ),
    )
    comparisons = run_scenarios(e1_request, baseline, [scenario], optimizer)
    from inventory_optimizer.reporting.tables import scenario_economics_table

    table = scenario_economics_table(comparisons)
    names = [row[1] for row in table.rows]
    assert names == sorted(comparisons[0].economics_component_deltas)


def test_stress_tables_row_per_outcome(e1_request, default_config) -> None:
    """AC-003."""
    optimizer = InventoryOptimizer(config=default_config)
    baseline = optimizer.optimize(e1_request)
    from inventory_optimizer.domain.enums import TradeEventType
    from inventory_optimizer.domain.scenarios import Scenario, TradeEvent

    event = TradeEvent(
        event_id="SALE-1",
        event_type=TradeEventType.SELL,
        trade_date=e1_request.effective_date,
        effective_date=e1_request.effective_date,
        settlement_date=e1_request.effective_date,
        quantity_shares=5.0,
        inventory_id="INV-1",
        source="fixture",
        source_version="v1",
    )
    scenario = Scenario(scenario_id="MILD-SALE", name="MILD-SALE", trade_events=(event,))
    report = run_stress_test(e1_request, baseline, [scenario], optimizer)

    tables = stress_tables(report)
    assert [t.name for t in tables] == ["stress_summary", "stress_outcomes"]
    summary, outcomes = tables
    assert len(summary.rows) == 1
    assert summary.rows[0][summary.columns.index("scenario_count")] == report.scenario_count
    assert len(outcomes.rows) == len(report.outcomes)
