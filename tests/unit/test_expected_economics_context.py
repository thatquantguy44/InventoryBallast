"""Expected-economics BuildContext tests (specs/0012-expected-economics-realism/: REQ-006)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from pydantic import ValidationError

from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.domain.economics import ExpectedEconomics
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.formulation.context import build_context
from inventory_optimizer.formulation.lp import compile_lp


def _estimate(**overrides: object) -> ExpectedEconomics:
    fields: dict[str, object] = dict(
        route_id="RT-A",
        take_up_probability=0.5,
        conditional_expected_days_active=0.5,
        manufactured_payment_cost_usd=0.10,
        indemnification_capital_cost_usd=0.20,
        settlement_fail_cost_usd=0.30,
        relationship_value_or_cost_usd=0.05,
        model_version="fixture-expected-economics-v1",
        calibration_date=date(2026, 1, 1),
        uncertainty=0.12,
    )
    fields.update(overrides)
    return ExpectedEconomics(**fields)


def _request_with_estimates(
    e1_request: OptimizationRequest,
    *estimates: ExpectedEconomics,
) -> OptimizationRequest:
    return OptimizationRequest.model_validate(
        {**e1_request.model_dump(), "expected_economics": estimates}
    )


def _assert_compiled_problem_equal(left, right) -> None:
    assert left.variable_index.keys == right.variable_index.keys
    assert left.row_index.keys == right.row_index.keys
    np.testing.assert_allclose(left.linear_objective, right.linear_objective)
    np.testing.assert_allclose(left.variable_lower, right.variable_lower)
    np.testing.assert_allclose(left.variable_upper, right.variable_upper)
    np.testing.assert_allclose(left.row_lower, right.row_lower)
    np.testing.assert_allclose(left.row_upper, right.row_upper)
    assert (left.constraint_matrix != right.constraint_matrix).nnz == 0


def test_expected_active_fraction_formula_and_clamp(
    e1_request: OptimizationRequest,
    default_config: InventoryOptimizerConfig,
) -> None:
    request = _request_with_estimates(
        e1_request,
        _estimate(
            route_id="RT-A",
            take_up_probability=0.5,
            conditional_expected_days_active=0.5,
        ),
        _estimate(
            route_id="RT-B",
            take_up_probability=1.0,
            conditional_expected_days_active=5.0,
        ),
    )

    context = build_context(request, default_config)

    assert context.expected_active_fractions["RT-A"] == pytest.approx(0.25)
    assert context.expected_active_fractions["RT-B"] == pytest.approx(1.0)


def test_expected_costs_are_precomputed_per_route(
    e1_request: OptimizationRequest,
    default_config: InventoryOptimizerConfig,
) -> None:
    request = _request_with_estimates(
        e1_request,
        _estimate(
            manufactured_payment_cost_usd=0.10,
            indemnification_capital_cost_usd=0.20,
            settlement_fail_cost_usd=0.30,
            relationship_value_or_cost_usd=0.05,
        ),
    )

    context = build_context(request, default_config)

    assert context.expected_costs["RT-A"] == pytest.approx(0.55)


def test_absent_estimates_leave_context_maps_empty(
    e1_request: OptimizationRequest,
    default_config: InventoryOptimizerConfig,
) -> None:
    context = build_context(e1_request, default_config)

    assert context.expected_economics_by_route == {}
    assert context.expected_active_fractions == {}
    assert context.expected_costs == {}


def test_expected_economics_does_not_change_compiled_problem(
    e1_request: OptimizationRequest,
    default_config: InventoryOptimizerConfig,
) -> None:
    baseline = compile_lp(e1_request, default_config)
    with_estimates = compile_lp(
        _request_with_estimates(e1_request, _estimate()),
        default_config,
    )

    _assert_compiled_problem_equal(baseline, with_estimates)


def test_request_rejects_duplicate_expected_economics_route_id(
    e1_request: OptimizationRequest,
) -> None:
    with pytest.raises(ValidationError):
        _request_with_estimates(e1_request, _estimate(), _estimate())
