"""Facade tests (T12; Section 17.1; specs/0003-public-api-cli/).

AC-001/AC-002 solve the real E1 fixture through ``InventoryOptimizer.optimize()`` (the composed
five-stage pipeline) rather than calling each stage directly, the way ``tests/golden/`` and
``tests/unit/test_solution_verifier.py`` already do. AC-003 confirms ``load_config()`` matches a
manual ``build_config``. AC-004 confirms ``input_hash`` is a genuine function of request content.
AC-005 confirms an unregistered solver backend fails closed before any solve is attempted. AC-006
confirms the ``platform`` argument passes through opaquely with no ``qr_haven`` import anywhere in
the call path.
"""

from __future__ import annotations

import sys

import pytest

from inventory_optimizer.domain.enums import SolverStatus
from inventory_optimizer.exceptions import ConfigurationError
from inventory_optimizer.facade import InventoryOptimizer, load_config
from inventory_optimizer.platform.context import PlatformInvocationContext


def test_optimize_returns_verified_optimal_result(e1_request, default_config) -> None:
    """AC-001."""
    optimizer = InventoryOptimizer(config=default_config)
    result = optimizer.optimize(e1_request)

    assert result.status is SolverStatus.OPTIMAL
    assert result.verification.passed is True


def test_optimize_is_deterministic_modulo_identity_fields(e1_request, default_config) -> None:
    """AC-002. NFR-001 excludes run_id/created_at/solver.runtime_seconds: the latter is
    wall-clock solve time, confirmed empirically to vary run-to-run even on an identical, tiny
    problem whose iteration count and termination reason do not (see spec.md's NFR-001 note)."""
    optimizer = InventoryOptimizer(config=default_config)
    first = optimizer.optimize(e1_request).model_dump(mode="json")
    second = optimizer.optimize(e1_request).model_dump(mode="json")

    for payload in (first, second):
        del payload["run_id"]
        del payload["created_at"]
        del payload["solver"]["runtime_seconds"]

    assert first == second


def test_load_config_matches_manual_build_config(default_config) -> None:
    """AC-003. ``default_config`` (tests/conftest.py) is itself
    ``build_config(defaults=load_yaml_file(configs/default.yaml))`` -- the same construction
    load_config() must reproduce with no explicit overrides."""
    assert load_config() == default_config


def test_input_hash_differs_on_request_change_matches_on_identical_request(
    e1_request, default_config
) -> None:
    """AC-004."""
    optimizer = InventoryOptimizer(config=default_config)

    changed_routes = tuple(
        route.model_copy(update={"fee_rate": route.fee_rate + 0.001})
        if route.route_id == "RT-A"
        else route
        for route in e1_request.routes
    )
    changed_request = e1_request.model_copy(update={"routes": changed_routes})

    result_original = optimizer.optimize(e1_request)
    result_changed = optimizer.optimize(changed_request)
    result_original_again = optimizer.optimize(e1_request)

    assert result_original.input_hash != result_changed.input_hash
    assert result_original.input_hash == result_original_again.input_hash


def test_unregistered_backend_raises_configuration_error(default_config) -> None:
    """AC-005."""
    bad_solver = default_config.solver.model_copy(update={"backend": "not-a-real-backend"})
    bad_config = default_config.model_copy(update={"solver": bad_solver})

    with pytest.raises(ConfigurationError):
        InventoryOptimizer(config=bad_config)


def test_platform_context_passthrough_no_qr_haven_import(e1_request, default_config) -> None:
    """AC-006."""
    context = PlatformInvocationContext(
        request_id=e1_request.request_id,
        correlation_id="corr-1",
        idempotency_key="idem-1",
        problem_family=e1_request.problem_family,
        as_of=e1_request.as_of,
        authorization_reference="auth-1",
        schema_version="1",
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(e1_request, platform=context)

    assert result.platform is context
    assert "qr_haven" not in sys.modules
