"""T18 QP compiler unit tests (specs/0007-qp-allocation-stability/): ``compile_lp``'s/
``compile_mip``'s new rejections, ``needs_qp``'s detection logic, ``compile_qp``'s exact
quadratic-matrix/scaling shape, and ``resolve_component``'s formulation-membership check --
mirroring ``test_mip_compiler.py``'s existing per-component style.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from inventory_optimizer.config.models import ObjectiveConfig
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import ConfigurationError, InputValidationError
from inventory_optimizer.formulation.compiler_support import needs_qp, resolve_component
from inventory_optimizer.formulation.indexes import VariableKey
from inventory_optimizer.formulation.lp import compile_lp
from inventory_optimizer.formulation.mip import compile_mip
from inventory_optimizer.formulation.qp import compile_qp

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)


def _single_route_request(inventory_factory, route_factory, demand_factory, **route_overrides):
    inventory = inventory_factory()
    route = route_factory("RT-A", "DG-A", fee_rate=0.02, **route_overrides)
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02)
    return OptimizationRequest(
        request_id="REQ-1",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
    )


def _config_with_penalty(default_config, penalty: float):
    return default_config.model_copy(
        update={"objective": ObjectiveConfig(allocation_stability_penalty=penalty)}
    )


def test_needs_qp_true_when_penalty_positive(default_config) -> None:
    assert needs_qp(_config_with_penalty(default_config, 0.01)) is True


def test_needs_qp_false_by_default(default_config) -> None:
    assert needs_qp(default_config) is False


def test_compile_lp_rejects_positive_penalty(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-004."""
    request = _single_route_request(inventory_factory, route_factory, demand_factory)
    config = _config_with_penalty(default_config, 0.01)

    with pytest.raises(InputValidationError) as excinfo:
        compile_lp(request, config)

    assert excinfo.value.issues[0].code == "QP_REQUIRED"
    assert excinfo.value.issues[0].location == "config.objective.allocation_stability_penalty"


def test_compile_mip_rejects_qp_conflict(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-005: compile_mip fails closed on a positive penalty even with no MIP trigger present."""
    request = _single_route_request(inventory_factory, route_factory, demand_factory)
    config = _config_with_penalty(default_config, 0.01)

    with pytest.raises(InputValidationError) as excinfo:
        compile_mip(request, config)

    assert excinfo.value.issues[0].code == "MIQP_UNSUPPORTED"


def test_compile_qp_rejects_mip_conflict(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """AC-005: compile_qp fails closed on a MIP-triggering route even with the penalty active."""
    request = _single_route_request(
        inventory_factory, route_factory, demand_factory, all_or_none=True
    )
    config = _config_with_penalty(default_config, 0.01)

    with pytest.raises(InputValidationError) as excinfo:
        compile_qp(request, config)

    assert excinfo.value.issues[0].code == "MIQP_UNSUPPORTED"


def test_compile_qp_quadratic_matrix_matches_hand_formula(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    request = _single_route_request(inventory_factory, route_factory, demand_factory)
    config = _config_with_penalty(default_config, 0.02)

    problem = compile_qp(request, config)

    assert problem.quadratic_objective is not None
    inc_col = problem.variable_index.position(VariableKey("inc", "RT-A"))
    dec_col = problem.variable_index.position(VariableKey("dec", "RT-A"))
    dense = problem.quadratic_objective.toarray()
    assert dense[inc_col, inc_col] == pytest.approx(0.02)
    assert dense[dec_col, dec_col] == pytest.approx(0.02)
    assert dense[inc_col, dec_col] == pytest.approx(-0.02)
    assert dense[dec_col, inc_col] == pytest.approx(-0.02)
    # every other entry is zero -- no cross-route or cross-inventory terms
    assert dense.sum() == pytest.approx(0.02 + 0.02 - 0.02 - 0.02)


def test_compile_qp_sets_scaling_metadata(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    request = _single_route_request(inventory_factory, route_factory, demand_factory)
    config = _config_with_penalty(default_config, 0.02)

    problem = compile_qp(request, config)

    assert problem.scaling.applied is True
    assert problem.scaling.objective_scale_usd == pytest.approx(1.0 / 0.02)


def test_compile_lp_never_applies_scaling(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    """NFR-001/NFR-003: compile_lp's own path never touches ScalingMetadata."""
    request = _single_route_request(inventory_factory, route_factory, demand_factory)

    problem = compile_lp(request, default_config)

    assert problem.scaling.applied is False
    assert problem.quadratic_objective is None


def test_resolve_component_rejects_wrong_formulation() -> None:
    """REQ-010: allocation_stability declares formulations={QP} only."""
    with pytest.raises(ConfigurationError):
        resolve_component("allocation_stability", formulation=Formulation.LP)


def test_resolve_component_accepts_declared_formulation() -> None:
    kind, registration = resolve_component("allocation_stability", formulation=Formulation.QP)
    assert registration.name == "allocation_stability"
