"""01_SPEC.md Section 24.6 -- "Hard utilization floor exceeds cap" infeasibility case
(specs/0005-test-hardening/spec.md AC-012).

Two independently-valid ``UtilizationPolicy`` records on the same inventory pool: one sets
``maximum_utilization=0.30`` alone, the other sets ``minimum_utilization=0.90`` alone. Neither
violates ``UtilizationPolicy``'s own single-record ordering check (each has only one of
min/target/max set), but ``UtilizationCapConstraint`` (T08) adds one row per policy, so the
*compiled* LP carries both ``q <= 0.30*L`` and ``q >= 0.90*L`` for the same routes -- mutually
exclusive for any positive ``L``. The conflict only exists in combination.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from inventory_optimizer.domain.enums import SolverStatus
from inventory_optimizer.domain.policies import UtilizationPolicy
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.facade import InventoryOptimizer

_AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_EFFECTIVE_DATE = date(2026, 9, 3)


def test_combined_utilization_floor_and_cap_is_infeasible(
    inventory_factory, route_factory, demand_factory, default_config
) -> None:
    inventory = inventory_factory(total_lendable_shares=100.0, available_to_lend_shares=100.0)
    route = route_factory("RT-A", "DG-A", fee_rate=0.02, maximum_quantity_shares=100.0)
    demand = demand_factory("DG-A", "BORROWER-RT-A", fee_rate=0.02, reference_quantity_shares=100.0)
    cap_policy = UtilizationPolicy(
        policy_id="UP-CAP",
        inventory_pool_id="POOL-1",
        effective_from=_AS_OF,
        maximum_utilization=0.30,
        source="fixture",
        source_version="v1",
    )
    floor_policy = UtilizationPolicy(
        policy_id="UP-FLOOR",
        inventory_pool_id="POOL-1",
        effective_from=_AS_OF,
        minimum_utilization=0.90,
        source="fixture",
        source_version="v1",
    )
    request = OptimizationRequest(
        request_id="REQ-UTIL-CONFLICT",
        as_of=_AS_OF,
        effective_date=_EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route,),
        demand=(demand,),
        utilization_policies=(cap_policy, floor_policy),
    )
    optimizer = InventoryOptimizer(config=default_config)

    result = optimizer.optimize(request)

    assert result.status is SolverStatus.INFEASIBLE
    assert result.allocations == ()
