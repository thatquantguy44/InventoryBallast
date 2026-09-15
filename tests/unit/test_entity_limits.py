"""Entity-scoped counterparty limit tests (specs/0012-expected-economics-realism/: REQ-003,
REQ-004)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.domain.policies import CounterpartyLimit
from inventory_optimizer.domain.reference import (
    DataQuality,
    EntityRelationship,
    PointInTimeValue,
)
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import InputValidationError
from inventory_optimizer.formulation.indexes import RowKey, VariableKey
from inventory_optimizer.formulation.lp import compile_lp

AS_OF = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
EFFECTIVE_DATE = date(2026, 9, 3)


def _relationship(
    borrower_id: str,
    *,
    legal_entity_id: str,
    ultimate_parent_id: str,
    confidence: float = 0.95,
    quality: DataQuality = DataQuality.VERIFIED,
) -> PointInTimeValue[EntityRelationship]:
    return PointInTimeValue[EntityRelationship](
        value=EntityRelationship(
            entity_id=borrower_id,
            legal_entity_id=legal_entity_id,
            ultimate_parent_id=ultimate_parent_id,
            relationship_type="borrower_to_parent",
            ownership_confidence=confidence,
        ),
        observed_at=AS_OF,
        effective_from=AS_OF,
        effective_to=None,
        source="fixture",
        source_version="v1",
        field_mapping_version="v1",
        quality=quality,
    )


def _entity_request(
    inventory_factory,
    route_factory,
    demand_factory,
    *,
    relationships: tuple[PointInTimeValue[EntityRelationship], ...],
    limit: CounterpartyLimit,
) -> OptimizationRequest:
    inventory = inventory_factory(total_lendable_shares=200.0, available_to_lend_shares=200.0)
    route_a = route_factory(
        "RT-A",
        "DG-A",
        fee_rate=0.02,
        borrower_id="BORROWER-A",
        maximum_quantity_shares=100.0,
    )
    route_b = route_factory(
        "RT-B",
        "DG-B",
        fee_rate=0.02,
        borrower_id="BORROWER-B",
        maximum_quantity_shares=100.0,
    )
    demand_a = demand_factory("DG-A", "BORROWER-A", fee_rate=0.02, reference_quantity_shares=100.0)
    demand_b = demand_factory("DG-B", "BORROWER-B", fee_rate=0.02, reference_quantity_shares=100.0)
    return OptimizationRequest(
        request_id="REQ-ENTITY",
        as_of=AS_OF,
        effective_date=EFFECTIVE_DATE,
        inventory=(inventory,),
        routes=(route_a, route_b),
        demand=(demand_a, demand_b),
        counterparty_limits=(limit,),
        entity_relationships=relationships,
    )


def test_parent_scoped_limit_aggregates_across_borrowers(
    inventory_factory,
    route_factory,
    demand_factory,
    default_config: InventoryOptimizerConfig,
) -> None:
    limit = CounterpartyLimit(
        limit_id="CL-PARENT",
        borrower_id="IGNORED-WHEN-PARENT-SCOPED",
        ultimate_parent_id="PARENT-1",
        effective_from=AS_OF,
        maximum_quantity_shares=90.0,
        source="fixture",
        source_version="v1",
    )
    request = _entity_request(
        inventory_factory,
        route_factory,
        demand_factory,
        relationships=(
            _relationship(
                "BORROWER-A", legal_entity_id="LE-A", ultimate_parent_id="PARENT-1"
            ),
            _relationship(
                "BORROWER-B", legal_entity_id="LE-B", ultimate_parent_id="PARENT-1"
            ),
        ),
        limit=limit,
    )

    problem = compile_lp(request, default_config)

    row = problem.row_index.position(RowKey("counterparty_quantity", "CL-PARENT"))
    assert problem.row_upper[row] == 90.0
    col_a = problem.variable_index.position(VariableKey("q", "RT-A"))
    col_b = problem.variable_index.position(VariableKey("q", "RT-B"))
    assert problem.constraint_matrix[row, col_a] == pytest.approx(1.0)
    assert problem.constraint_matrix[row, col_b] == pytest.approx(1.0)


def test_legal_entity_scoped_limit_uses_legal_entity_membership(
    inventory_factory,
    route_factory,
    demand_factory,
    default_config: InventoryOptimizerConfig,
) -> None:
    limit = CounterpartyLimit(
        limit_id="CL-LE",
        borrower_id="IGNORED-WHEN-ENTITY-SCOPED",
        legal_entity_id="LE-1",
        effective_from=AS_OF,
        maximum_notional_usd=500.0,
        source="fixture",
        source_version="v1",
    )
    request = _entity_request(
        inventory_factory,
        route_factory,
        demand_factory,
        relationships=(
            _relationship("BORROWER-A", legal_entity_id="LE-1", ultimate_parent_id="PARENT-A"),
            _relationship("BORROWER-B", legal_entity_id="LE-2", ultimate_parent_id="PARENT-B"),
        ),
        limit=limit,
    )

    problem = compile_lp(request, default_config)

    row = problem.row_index.position(RowKey("counterparty_notional", "CL-LE"))
    col_a = problem.variable_index.position(VariableKey("q", "RT-A"))
    col_b = problem.variable_index.position(VariableKey("q", "RT-B"))
    assert problem.constraint_matrix[row, col_a] == pytest.approx(10.0)
    assert problem.constraint_matrix[row, col_b] == pytest.approx(0.0)


def test_low_confidence_mapping_fails_closed_for_hard_limit(
    inventory_factory,
    route_factory,
    demand_factory,
    default_config: InventoryOptimizerConfig,
) -> None:
    limit = CounterpartyLimit(
        limit_id="CL-PARENT",
        borrower_id="IGNORED-WHEN-PARENT-SCOPED",
        ultimate_parent_id="PARENT-1",
        effective_from=AS_OF,
        maximum_quantity_shares=90.0,
        hard=True,
        source="fixture",
        source_version="v1",
    )
    request = _entity_request(
        inventory_factory,
        route_factory,
        demand_factory,
        relationships=(
            _relationship(
                "BORROWER-A",
                legal_entity_id="LE-A",
                ultimate_parent_id="PARENT-1",
                confidence=0.25,
            ),
        ),
        limit=limit,
    )

    with pytest.raises(InputValidationError) as excinfo:
        compile_lp(request, default_config)

    issue = excinfo.value.issues[0]
    assert issue.code == "ENTITY_MAPPING_LOW_CONFIDENCE"
    assert "BORROWER-A" in issue.message
    assert "CL-PARENT" in issue.message


def test_unresolved_mapping_fails_closed_for_hard_limit(
    inventory_factory,
    route_factory,
    demand_factory,
    default_config: InventoryOptimizerConfig,
) -> None:
    limit = CounterpartyLimit(
        limit_id="CL-PARENT",
        borrower_id="IGNORED-WHEN-PARENT-SCOPED",
        ultimate_parent_id="PARENT-1",
        effective_from=AS_OF,
        maximum_quantity_shares=90.0,
        hard=True,
        source="fixture",
        source_version="v1",
    )
    request = _entity_request(
        inventory_factory,
        route_factory,
        demand_factory,
        relationships=(),
        limit=limit,
    )

    with pytest.raises(InputValidationError) as excinfo:
        compile_lp(request, default_config)

    assert {issue.code for issue in excinfo.value.issues} == {"ENTITY_MAPPING_UNRESOLVED"}


def test_soft_entity_limit_warns_on_unresolved_mapping(
    inventory_factory,
    route_factory,
    demand_factory,
    default_config: InventoryOptimizerConfig,
) -> None:
    limit = CounterpartyLimit(
        limit_id="CL-SOFT",
        borrower_id="IGNORED-WHEN-PARENT-SCOPED",
        ultimate_parent_id="PARENT-1",
        effective_from=AS_OF,
        maximum_quantity_shares=90.0,
        hard=False,
        source="fixture",
        source_version="v1",
    )
    request = _entity_request(
        inventory_factory,
        route_factory,
        demand_factory,
        relationships=(),
        limit=limit,
    )

    with pytest.warns(RuntimeWarning, match="CL-SOFT"):
        compile_lp(request, default_config)
