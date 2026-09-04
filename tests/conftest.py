"""Shared fixtures for inventory_optimizer tests.

``e1_request`` builds the E1 "Scarce-Name Allocation" fixture from ``specs/spec002/EXAMPLES.md``:
100 lendable shares, no reserve/committed, a 90% utilization cap, and two candidate routes (A at
2.00% fee, B at 1.00% fee) each demanding up to 80 shares. ``tests/golden/`` compiles it through
``formulation.lp.compile_lp`` and checks the exact allocation.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from inventory_optimizer.config import InventoryOptimizerConfig, build_config, load_yaml_file
from inventory_optimizer.domain.demand import DemandForecast
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.policies import UtilizationPolicy
from inventory_optimizer.domain.requests import OptimizationRequest

AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
EFFECTIVE_DATE = date(2026, 9, 3)
DEFAULT_YAML_PATH = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"


def make_inventory(**overrides: object) -> SecurityInventory:
    fields: dict[str, object] = dict(
        inventory_id="INV-1",
        inventory_pool_id="POOL-1",
        security_id="SEC-1",
        as_of=AS_OF,
        settlement_date=EFFECTIVE_DATE,
        total_lendable_shares=100.0,
        on_loan_shares=0.0,
        reserved_shares=0.0,
        committed_out_shares=0.0,
        available_to_lend_shares=100.0,
        price_usd=10.0,
        currency="USD",
        eligible=True,
        source_version="fixture-v1",
    )
    fields.update(overrides)
    return SecurityInventory(**fields)


def make_route(
    route_id: str, demand_group_id: str, fee_rate: float, **overrides: object
) -> LoanRoute:
    fields: dict[str, object] = dict(
        route_id=route_id,
        inventory_id="INV-1",
        security_id="SEC-1",
        borrower_id=f"BORROWER-{route_id}",
        demand_group_id=demand_group_id,
        current_quantity_shares=0.0,
        hard_minimum_quantity_shares=0.0,
        maximum_quantity_shares=80.0,
        fee_rate=fee_rate,
        revenue_share=1.0,
        variable_cost_rate=0.0,
        increase_cost_usd_per_share=0.0,
        decrease_cost_usd_per_share=0.0,
        recall_notice_days=0,
        term_end_date=None,
        eligible=True,
        all_or_none=False,
    )
    fields.update(overrides)
    return LoanRoute(**fields)


def make_demand(
    demand_group_id: str, borrower_id: str, fee_rate: float, **overrides: object
) -> DemandForecast:
    fields: dict[str, object] = dict(
        demand_group_id=demand_group_id,
        security_id="SEC-1",
        borrower_id=borrower_id,
        as_of=AS_OF,
        reference_quantity_shares=80.0,
        reference_fee_rate=fee_rate,
        elasticity=0.0,
        source_model="fixture",
        source_version="fixture-v1",
    )
    fields.update(overrides)
    return DemandForecast(**fields)


@pytest.fixture
def inventory_factory():
    """Factory fixture so other test files don't need to import this conftest module directly."""
    return make_inventory


@pytest.fixture
def route_factory():
    return make_route


@pytest.fixture
def demand_factory():
    return make_demand


@pytest.fixture
def e1_request() -> OptimizationRequest:
    route_a = make_route("RT-A", "DG-A", fee_rate=0.02)
    route_b = make_route("RT-B", "DG-B", fee_rate=0.01)
    demand_a = make_demand("DG-A", "BORROWER-RT-A", fee_rate=0.02)
    demand_b = make_demand("DG-B", "BORROWER-RT-B", fee_rate=0.01)
    utilization = UtilizationPolicy(
        policy_id="UP-1",
        inventory_pool_id="POOL-1",
        effective_from=AS_OF,
        maximum_utilization=0.90,
        source="fixture",
        source_version="fixture-v1",
    )
    return OptimizationRequest(
        request_id="REQ-E1",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(make_inventory(),),
        routes=(route_a, route_b),
        demand=(demand_a, demand_b),
        utilization_policies=(utilization,),
    )


@pytest.fixture
def default_config() -> InventoryOptimizerConfig:
    return build_config(defaults=load_yaml_file(DEFAULT_YAML_PATH))
