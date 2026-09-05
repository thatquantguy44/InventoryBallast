"""Service protocol tests (T12; Section 17.2; specs/0003-public-api-cli/)."""

from __future__ import annotations

from inventory_optimizer.domain.enums import ReasonCode
from inventory_optimizer.facade import InventoryOptimizer
from inventory_optimizer.services import ExplanationServiceImpl, OptimizationService


def test_inventory_optimizer_satisfies_optimization_service_protocol(default_config) -> None:
    """AC-007. Structural check -- ``InventoryOptimizer`` never subclasses the Protocol."""
    optimizer = InventoryOptimizer(config=default_config)

    assert isinstance(optimizer, OptimizationService)
    # Structural typing, not explicit inheritance: InventoryOptimizer's only base is `object`.
    # (`issubclass(InventoryOptimizer, OptimizationService)` is also True for a runtime_checkable
    # Protocol purely because the method shape matches -- that's the point of AC-007, not a
    # separate thing to disprove.)
    assert InventoryOptimizer.__bases__ == (object,)


def test_explanation_service_reads_result_without_resolving(e1_request, default_config) -> None:
    """AC-008. E1's own RT-A carries a binding demand cap and the higher fee-revenue coefficient
    (see tests/unit/reporting/test_explanations.py) -- ``explain()`` must surface both codes
    reading only the already-built ``OptimizationResult``."""
    optimizer = InventoryOptimizer(config=default_config)
    result = optimizer.optimize(e1_request)

    explanation = ExplanationServiceImpl().explain(result)

    assert explanation.run_id == result.run_id
    route_ids = {route.route_id for route in explanation.routes_with_reasons}
    assert "RT-A" in route_ids
    rt_a = next(route for route in explanation.routes_with_reasons if route.route_id == "RT-A")
    assert ReasonCode.HIGHER_NET_FEE in rt_a.reason_codes
    assert ReasonCode.DEMAND_CAP_BINDING in rt_a.reason_codes
    assert explanation.reason_code_counts[ReasonCode.HIGHER_NET_FEE] >= 1
