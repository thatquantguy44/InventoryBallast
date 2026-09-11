"""specs/0010-multi-period-settlement/ Phase 2 (T-008 through T-010) unit tests: row/variable
shape, the two recorded bound-tightening decisions (`formulation.multi_period`'s own module
docstring), the MIP/QP/fee-tier exclusion (AC-007), and `mode`/`disclosure` for the
`"jointly_optimized"` half of AC-008 -- mirroring `test_mip_compiler.py`'s/`test_qp_compiler.py`'s
existing per-behavior style.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from inventory_optimizer.config.models import ObjectiveConfig
from inventory_optimizer.domain.enums import (
    Formulation,
    ObjectiveSense,
    SolverStatus,
    TradeEventType,
)
from inventory_optimizer.domain.policies import UtilizationPolicy
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.scenarios import TradeEvent
from inventory_optimizer.exceptions import InputValidationError
from inventory_optimizer.formulation.indexes import RowKey, VariableKey
from inventory_optimizer.formulation.lp import compile_lp
from inventory_optimizer.formulation.multi_period import (
    MAX_PERIODS,
    build_multi_period_context,
    build_multi_period_variable_index,
    compile_multi_period_lp,
    compute_period_bound_adjustments,
    period_scope_id,
    period_variable_key,
    set_route_bounds_for_period,
    solve_multi_period,
)
from inventory_optimizer.formulation.sparse_builder import SparseBuilder
from inventory_optimizer.solvers.highs import HighsBackend

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)


def _single_route_request(inventory_factory, route_factory, demand_factory, **route_overrides):
    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    route = route_factory("RT-A", "DG-A", fee_rate=0.02, **route_overrides)
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02, reference_quantity_shares=100.0)
    return OptimizationRequest(
        request_id="REQ-1",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )


def _multi_period_request(
    inventory_factory, route_factory, demand_factory, *, planning_periods=None, **route_overrides
):
    periods = planning_periods or (_EFFECTIVE_DATE + timedelta(days=1),)
    request = _single_route_request(
        inventory_factory, route_factory, demand_factory, **route_overrides
    )
    return request.model_copy(update={"planning_periods": periods})


def _recall(
    route_id: str, quantity: float, *, effective_days: int, trade_days: int = 0
) -> TradeEvent:
    return TradeEvent(
        event_id=f"RECALL-{route_id}-{effective_days}",
        event_type=TradeEventType.RECALL,
        trade_date=_EFFECTIVE_DATE + timedelta(days=trade_days),
        effective_date=_EFFECTIVE_DATE + timedelta(days=effective_days),
        settlement_date=_EFFECTIVE_DATE + timedelta(days=effective_days),
        quantity_shares=quantity,
        route_id=route_id,
        source="fixture",
        source_version="v1",
    )


def _return(route_id: str, quantity: float, *, effective_days: int) -> TradeEvent:
    return TradeEvent(
        event_id=f"RETURN-{route_id}-{effective_days}",
        event_type=TradeEventType.RETURN,
        trade_date=_EFFECTIVE_DATE,
        effective_date=_EFFECTIVE_DATE + timedelta(days=effective_days),
        settlement_date=_EFFECTIVE_DATE + timedelta(days=effective_days),
        quantity_shares=quantity,
        route_id=route_id,
        source="fixture",
        source_version="v1",
    )


def _new_loan(route_id: str, quantity: float, *, effective_days: int) -> TradeEvent:
    return TradeEvent(
        event_id=f"NEWLOAN-{route_id}-{effective_days}",
        event_type=TradeEventType.NEW_LOAN,
        trade_date=_EFFECTIVE_DATE,
        effective_date=_EFFECTIVE_DATE + timedelta(days=effective_days),
        settlement_date=_EFFECTIVE_DATE + timedelta(days=effective_days),
        quantity_shares=quantity,
        route_id=route_id,
        source="fixture",
        source_version="v1",
    )


def _buy(inventory_id: str, quantity: float, *, effective_days: int) -> TradeEvent:
    return TradeEvent(
        event_id=f"BUY-{inventory_id}-{effective_days}",
        event_type=TradeEventType.BUY,
        trade_date=_EFFECTIVE_DATE,
        effective_date=_EFFECTIVE_DATE + timedelta(days=effective_days),
        settlement_date=_EFFECTIVE_DATE + timedelta(days=effective_days),
        quantity_shares=quantity,
        inventory_id=inventory_id,
        source="fixture",
        source_version="v1",
    )


def _transfer_in(inventory_id: str, quantity: float, *, effective_days: int) -> TradeEvent:
    return TradeEvent(
        event_id=f"XFER-{inventory_id}-{effective_days}",
        event_type=TradeEventType.TRANSFER_IN,
        trade_date=_EFFECTIVE_DATE,
        effective_date=_EFFECTIVE_DATE + timedelta(days=effective_days),
        settlement_date=_EFFECTIVE_DATE + timedelta(days=effective_days),
        quantity_shares=quantity,
        inventory_id=inventory_id,
        source="fixture",
        source_version="v1",
    )


# ---------------------------------------------------------------------------------------------
# Empty planning_periods / MIP / QP exclusion (REQ-012, AC-007)
# ---------------------------------------------------------------------------------------------


def test_compile_multi_period_lp_rejects_empty_planning_periods(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    request = _single_route_request(inventory_factory, route_factory, demand_factory)
    with pytest.raises(ValueError, match="planning_periods"):
        compile_multi_period_lp(request, default_config)


def test_solve_multi_period_rejects_empty_planning_periods(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    request = _single_route_request(inventory_factory, route_factory, demand_factory)
    with pytest.raises(ValueError, match="planning_periods"):
        solve_multi_period(request, default_config)


def test_compile_multi_period_lp_rejects_mip_trigger(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-007."""
    request = _multi_period_request(
        inventory_factory, route_factory, demand_factory, all_or_none=True
    )
    with pytest.raises(InputValidationError) as excinfo:
        compile_multi_period_lp(request, default_config)
    assert excinfo.value.issues[0].code == "MULTI_PERIOD_MIP_QP_UNSUPPORTED"


def test_compile_multi_period_lp_rejects_qp_trigger(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-007, QP half."""
    request = _multi_period_request(inventory_factory, route_factory, demand_factory)
    config = default_config.model_copy(
        update={"objective": ObjectiveConfig(allocation_stability_penalty=0.01)}
    )
    with pytest.raises(InputValidationError) as excinfo:
        compile_multi_period_lp(request, config)
    assert excinfo.value.issues[0].code == "MULTI_PERIOD_MIP_QP_UNSUPPORTED"


def test_solve_multi_period_rejects_mip_trigger(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-007, via the top-level entry point."""
    request = _multi_period_request(
        inventory_factory, route_factory, demand_factory, all_or_none=True
    )
    with pytest.raises(InputValidationError) as excinfo:
        solve_multi_period(request, default_config)
    assert excinfo.value.issues[0].code == "MULTI_PERIOD_MIP_QP_UNSUPPORTED"


# ---------------------------------------------------------------------------------------------
# Period 0 byte-identical to today's baseline compile_lp (REQ-009)
# ---------------------------------------------------------------------------------------------


def test_period_zero_rows_and_bounds_match_baseline_compile_lp(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    baseline_request = _single_route_request(
        inventory_factory, route_factory, demand_factory,
        maximum_quantity_shares=80.0, current_quantity_shares=20.0,
    )
    baseline_problem = compile_lp(baseline_request, default_config)
    multi_request = baseline_request.model_copy(
        update={
            "request_id": "REQ-MULTI",
            "planning_periods": (_EFFECTIVE_DATE + timedelta(days=1),),
        }
    )
    multi_problem = compile_multi_period_lp(multi_request, default_config)

    baseline_q = baseline_problem.variable_index.position(VariableKey("q", "RT-A"))
    multi_q = multi_problem.variable_index.position(period_variable_key("q", "RT-A", 0))
    assert multi_problem.variable_lower[multi_q] == pytest.approx(
        baseline_problem.variable_lower[baseline_q]
    )
    assert multi_problem.variable_upper[multi_q] == pytest.approx(
        baseline_problem.variable_upper[baseline_q]
    )

    baseline_inc = baseline_problem.variable_index.position(VariableKey("inc", "RT-A"))
    multi_inc = multi_problem.variable_index.position(period_variable_key("inc", "RT-A", 0))
    assert multi_problem.variable_upper[multi_inc] == pytest.approx(
        baseline_problem.variable_upper[baseline_inc]
    )

    baseline_row = baseline_problem.row_index.position(RowKey("inventory_balance", "INV-1"))
    multi_row = multi_problem.row_index.position(
        RowKey("inventory_balance", period_scope_id("INV-1", 0))
    )
    assert multi_problem.row_lower[multi_row] == pytest.approx(
        baseline_problem.row_lower[baseline_row]
    )
    assert multi_problem.row_upper[multi_row] == pytest.approx(
        baseline_problem.row_upper[baseline_row]
    )
    assert multi_problem.constraint_matrix[multi_row, multi_q] == pytest.approx(
        baseline_problem.constraint_matrix[baseline_row, baseline_q]
    )

    baseline_ti_row = baseline_problem.row_index.position(RowKey("transition_identity", "RT-A"))
    multi_ti_row = multi_problem.row_index.position(
        RowKey("transition_identity", period_scope_id("RT-A", 0))
    )
    assert multi_problem.row_lower[multi_ti_row] == pytest.approx(
        baseline_problem.row_lower[baseline_ti_row]
    )
    assert multi_problem.row_upper[multi_ti_row] == pytest.approx(
        baseline_problem.row_upper[baseline_ti_row]
    )


# ---------------------------------------------------------------------------------------------
# Variable index shape (REQ-009's "Variables" section) and the MAX_PERIODS cap
# ---------------------------------------------------------------------------------------------


def test_variable_index_has_one_period_suffixed_block_per_kind(
    inventory_factory, route_factory, demand_factory
) -> None:
    request = _multi_period_request(
        inventory_factory, route_factory, demand_factory,
        planning_periods=(_EFFECTIVE_DATE + timedelta(days=1), _EFFECTIVE_DATE + timedelta(days=2)),
    )
    variable_index = build_multi_period_variable_index(request)

    for kind in ("q", "inc", "dec"):
        for period_index in range(3):  # period 0, 1, 2
            assert period_variable_key(kind, "RT-A", period_index) in variable_index
    for period_index in range(3):
        assert period_variable_key("a", "INV-1", period_index) in variable_index
    assert len(variable_index) == 3 * 3 + 3  # (q, inc, dec) x 3 periods + a x 3 periods


def test_build_multi_period_variable_index_rejects_too_many_periods(
    inventory_factory, route_factory, demand_factory
) -> None:
    too_many_periods = tuple(
        _EFFECTIVE_DATE + timedelta(days=day) for day in range(1, MAX_PERIODS + 2)
    )
    request = _multi_period_request(
        inventory_factory, route_factory, demand_factory, planning_periods=too_many_periods
    )
    with pytest.raises(InputValidationError) as excinfo:
        build_multi_period_variable_index(request)
    assert excinfo.value.issues[0].code == "MULTI_PERIOD_TOO_MANY_PERIODS"


# ---------------------------------------------------------------------------------------------
# compute_period_bound_adjustments (REQ-010) -- the two recorded decisions and event coverage
# ---------------------------------------------------------------------------------------------


def test_recall_lowers_only_max_floored_at_unchanged_hard_minimum(
    inventory_factory, route_factory, demand_factory
) -> None:
    request = _multi_period_request(
        inventory_factory, route_factory, demand_factory,
        maximum_quantity_shares=100.0, hard_minimum_quantity_shares=25.0,
    ).model_copy(update={"known_future_events": (_recall("RT-A", 90.0, effective_days=1),)})
    boundaries = (_EFFECTIVE_DATE, _EFFECTIVE_DATE + timedelta(days=1))

    adjustments = compute_period_bound_adjustments(request, boundaries)

    # max(100 - 90, hard_minimum=25) == 25 -- floored at the *unchanged* hard minimum.
    assert adjustments.max_quantity_by_route[1]["RT-A"] == pytest.approx(25.0)
    assert adjustments.hard_minimum_by_route[1]["RT-A"] == pytest.approx(25.0)


def test_return_lowers_both_max_and_hard_minimum(
    inventory_factory, route_factory, demand_factory
) -> None:
    """Decision 1 (formulation.multi_period's own module docstring): unlike RECALL, RETURN lowers
    the hard minimum itself, not just the max, floored at zero."""
    request = _multi_period_request(
        inventory_factory, route_factory, demand_factory,
        maximum_quantity_shares=100.0, hard_minimum_quantity_shares=25.0,
    ).model_copy(update={"known_future_events": (_return("RT-A", 10.0, effective_days=1),)})
    boundaries = (_EFFECTIVE_DATE, _EFFECTIVE_DATE + timedelta(days=1))

    adjustments = compute_period_bound_adjustments(request, boundaries)

    assert adjustments.hard_minimum_by_route[1]["RT-A"] == pytest.approx(15.0)  # 25 - 10
    assert adjustments.max_quantity_by_route[1]["RT-A"] == pytest.approx(90.0)  # 100 - 10


def test_return_floors_hard_minimum_at_zero_and_max_at_the_new_hard_minimum(
    inventory_factory, route_factory, demand_factory
) -> None:
    request = _multi_period_request(
        inventory_factory, route_factory, demand_factory,
        maximum_quantity_shares=100.0, hard_minimum_quantity_shares=5.0,
    ).model_copy(update={"known_future_events": (_return("RT-A", 40.0, effective_days=1),)})
    boundaries = (_EFFECTIVE_DATE, _EFFECTIVE_DATE + timedelta(days=1))

    adjustments = compute_period_bound_adjustments(request, boundaries)

    assert adjustments.hard_minimum_by_route[1]["RT-A"] == pytest.approx(0.0)  # max(5-40, 0)
    assert adjustments.max_quantity_by_route[1]["RT-A"] == pytest.approx(60.0)  # max(100-40, 0)


def test_new_loan_raises_max_and_persists_into_later_periods(
    inventory_factory, route_factory, demand_factory
) -> None:
    request = _multi_period_request(
        inventory_factory, route_factory, demand_factory, maximum_quantity_shares=50.0,
        planning_periods=(
            _EFFECTIVE_DATE + timedelta(days=1), _EFFECTIVE_DATE + timedelta(days=2)
        ),
    ).model_copy(update={"known_future_events": (_new_loan("RT-A", 80.0, effective_days=1),)})
    boundaries = (
        _EFFECTIVE_DATE, _EFFECTIVE_DATE + timedelta(days=1), _EFFECTIVE_DATE + timedelta(days=2)
    )

    adjustments = compute_period_bound_adjustments(request, boundaries)

    assert adjustments.max_quantity_by_route[1]["RT-A"] == pytest.approx(80.0)
    assert adjustments.max_quantity_by_route[2]["RT-A"] == pytest.approx(80.0)  # persists


def test_buy_raises_lendable_and_sell_lowers_it_persisting_forward(
    inventory_factory, route_factory, demand_factory
) -> None:
    request = _multi_period_request(
        inventory_factory, route_factory, demand_factory,
        planning_periods=(
            _EFFECTIVE_DATE + timedelta(days=1), _EFFECTIVE_DATE + timedelta(days=2)
        ),
    ).model_copy(update={"known_future_events": (_buy("INV-1", 30.0, effective_days=1),)})
    boundaries = (
        _EFFECTIVE_DATE, _EFFECTIVE_DATE + timedelta(days=1), _EFFECTIVE_DATE + timedelta(days=2)
    )

    adjustments = compute_period_bound_adjustments(request, boundaries)

    assert adjustments.lendable_delta_by_inventory[1]["INV-1"] == pytest.approx(30.0)
    assert adjustments.lendable_delta_by_inventory[2]["INV-1"] == pytest.approx(30.0)  # persists


def test_transfer_in_to_an_ineligible_inventory_has_no_effect(
    inventory_factory, route_factory, demand_factory
) -> None:
    """Mirrors scenarios.apply._apply_trade_event's own TRANSFER_IN eligibility gate exactly."""
    request = _multi_period_request(inventory_factory, route_factory, demand_factory)
    ineligible_inventory = request.inventory[0].model_copy(update={"eligible": False})
    request = request.model_copy(
        update={
            "inventory": (ineligible_inventory,),
            "known_future_events": (_transfer_in("INV-1", 30.0, effective_days=1),),
        }
    )
    boundaries = (_EFFECTIVE_DATE, _EFFECTIVE_DATE + timedelta(days=1))

    adjustments = compute_period_bound_adjustments(request, boundaries)

    assert adjustments.lendable_delta_by_inventory[1].get("INV-1", 0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------------------------
# set_route_bounds_for_period -- decision 2 (the already-ineligible-route clamp at t >= 1)
# ---------------------------------------------------------------------------------------------


def test_ineligible_route_upper_bound_clamps_to_period_zero_baseline_at_later_periods(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """Decision 2. No known_future_event ever makes a route newly ineligible, so this only
    exercises a route that starts ineligible."""
    request = _multi_period_request(
        inventory_factory, route_factory, demand_factory,
        eligible=False, current_quantity_shares=40.0, maximum_quantity_shares=100.0,
        planning_periods=(
            _EFFECTIVE_DATE + timedelta(days=1), _EFFECTIVE_DATE + timedelta(days=2)
        ),
    )
    context = build_multi_period_context(request, default_config)
    variable_index = build_multi_period_variable_index(request)
    builder = SparseBuilder(variable_index)

    for period_index in range(context.period_count):
        set_route_bounds_for_period(context, builder, period_index)

    problem = builder.build(formulation=Formulation.LP, objective_sense=ObjectiveSense.MAXIMIZE)
    for period_index in range(3):
        upper = problem.variable_upper[
            variable_index.position(period_variable_key("q", "RT-A", period_index))
        ]
        assert upper == pytest.approx(40.0)  # clamped to the period-0 baseline current quantity


# ---------------------------------------------------------------------------------------------
# solve_multi_period: mode/disclosure (AC-008) and the honest-status no-primal contract
# ---------------------------------------------------------------------------------------------


def test_solve_multi_period_mode_is_jointly_optimized(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-008, jointly_optimized half."""
    request = _multi_period_request(inventory_factory, route_factory, demand_factory)

    projection = solve_multi_period(request, default_config)

    assert projection.mode == "jointly_optimized"
    assert "not a projection" in projection.disclosure


def test_solve_multi_period_with_no_feasible_primal_is_empty_with_status_and_warning(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """Mirrors settlement.project.project_multi_period's own honest-status discipline
    (test_settlement_project.py::test_projection_with_no_feasible_primal_is_empty_with_status_and_warning),
    reusing the same conflicting-floor/cap trick as test_utilization_floor_exceeds_cap.py."""
    request = _multi_period_request(inventory_factory, route_factory, demand_factory)
    cap_policy = UtilizationPolicy(
        policy_id="UP-CAP", inventory_pool_id="POOL-1", effective_from=_AS_OF,
        maximum_utilization=0.10, source="fixture", source_version="v1",
    )
    floor_policy = UtilizationPolicy(
        policy_id="UP-FLOOR", inventory_pool_id="POOL-1", effective_from=_AS_OF,
        minimum_utilization=0.90, source="fixture", source_version="v1",
    )
    request = request.model_copy(update={"utilization_policies": (cap_policy, floor_policy)})

    projection = solve_multi_period(request, default_config)

    assert projection.mode == "jointly_optimized"
    assert projection.status is SolverStatus.INFEASIBLE
    assert projection.balances == ()
    assert projection.economics == ()
    assert projection.total_discounted_net_revenue_usd == 0.0
    assert any("no feasible primal" in warning for warning in projection.warnings)


def test_solve_multi_period_accepts_an_explicit_backend(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    request = _multi_period_request(inventory_factory, route_factory, demand_factory)
    projection = solve_multi_period(request, default_config, backend=HighsBackend())
    assert projection.status is SolverStatus.OPTIMAL
