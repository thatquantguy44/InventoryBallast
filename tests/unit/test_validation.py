"""Cross-record validation (Section 9.8 invariants 1, 2, 6, 8, 9, 10; Section 12.2 fee
consistency) and aggregation behavior."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.exceptions import InputValidationError
from inventory_optimizer.validation import raise_if_invalid, validate_request


def test_e1_request_has_no_issues(e1_request: OptimizationRequest) -> None:
    assert validate_request(e1_request) == ()
    raise_if_invalid(e1_request)  # must not raise


def test_aggregates_every_independent_issue_in_one_pass(e1_request: OptimizationRequest) -> None:
    # Introduce four independent problems at once: an on-loan mismatch (route B's current
    # quantity no longer matches inventory.on_loan_shares), a security mismatch on route A, an
    # expired term on route A, and a demand-group borrower mismatch on route B.
    broken_route_a = e1_request.routes[0].model_copy(
        update={"security_id": "SEC-OTHER", "term_end_date": date(2020, 1, 1)}
    )
    broken_route_b = e1_request.routes[1].model_copy(update={"current_quantity_shares": 5.0})
    broken_demand_b = e1_request.demand[1].model_copy(update={"borrower_id": "SOMEONE-ELSE"})

    broken_request = e1_request.model_copy(
        update={
            "routes": (broken_route_a, broken_route_b),
            "demand": (e1_request.demand[0], broken_demand_b),
        }
    )

    issues = validate_request(broken_request)
    codes = {issue.code for issue in issues}

    assert "INVENTORY_SECURITY_MISMATCH" in codes
    assert "TERM_ALREADY_EXPIRED" in codes
    assert "ON_LOAN_RECONCILIATION_FAILED" in codes
    assert "DEMAND_GROUP_BORROWER_MISMATCH" in codes
    assert len(issues) >= 4

    with pytest.raises(InputValidationError) as excinfo:
        raise_if_invalid(broken_request)
    assert set(codes) <= {issue.code for issue in excinfo.value.issues}


def test_duplicate_route_id_is_reported(e1_request: OptimizationRequest) -> None:
    duplicated = e1_request.routes[1].model_copy(update={"route_id": e1_request.routes[0].route_id})
    broken_request = e1_request.model_copy(update={"routes": (e1_request.routes[0], duplicated)})

    issues = validate_request(broken_request)
    assert any(issue.code == "DUPLICATE_ID" for issue in issues)


def test_unresolved_foreign_key_is_reported(e1_request: OptimizationRequest, route_factory) -> None:
    dangling = route_factory("RT-DANGLING", "DG-NOWHERE", fee_rate=0.02)
    broken_request = e1_request.model_copy(update={"routes": (*e1_request.routes, dangling)})

    issues = validate_request(broken_request)
    assert any(
        issue.code == "UNRESOLVED_FOREIGN_KEY" and "demand_group_id" in issue.location
        for issue in issues
    )


def test_stale_inventory_as_of_is_reported(e1_request: OptimizationRequest) -> None:
    stale_inventory = e1_request.inventory[0].model_copy(
        update={"as_of": e1_request.as_of - timedelta(hours=48)}
    )
    broken_request = e1_request.model_copy(update={"inventory": (stale_inventory,)})

    issues = validate_request(broken_request, max_staleness_hours=24.0)
    assert any(issue.code == "STALE_OR_FUTURE_AS_OF" for issue in issues)


def test_demand_group_fee_inconsistency_is_reported(
    e1_request: OptimizationRequest, route_factory
) -> None:
    # Section 12.2: routes sharing a demand group must share one evaluated fee. A second route on
    # DG-A at a different fee_rate implies a different borrower price choice, which the spec says
    # requires a distinct demand group or the discrete pricing MIP -- not a single LP demand cap.
    second_route_same_group = route_factory(
        "RT-A2", "DG-A", fee_rate=0.05, borrower_id="BORROWER-RT-A"
    )
    broken_request = e1_request.model_copy(
        update={"routes": (*e1_request.routes, second_route_same_group)}
    )

    issues = validate_request(broken_request)
    assert any(issue.code == "DEMAND_GROUP_FEE_INCONSISTENT" for issue in issues)
