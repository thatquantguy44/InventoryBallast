"""Decision explanation tests (T11; Section 18.3; VER-005).

AC-005/AC-006 solve the real E1 fixture: RT-A (2% fee) is the higher-coefficient route sharing
INV-1 with RT-B (1% fee), and its demand-group cap binds exactly at its solved quantity, so both
codes must fire with evidence. AC-007 uses a route contractually pinned at its current quantity
(cannot move regardless of how attractive its fee looks) to prove the "material change" gate
actually suppresses codes rather than firing on every route unconditionally.
"""

from __future__ import annotations

import pytest

from inventory_optimizer.domain.enums import ReasonCode
from inventory_optimizer.reporting.explanations import explain_routes
from inventory_optimizer.reporting.types import VerifiedSolution
from inventory_optimizer.validation import DEFAULT_TOLERANCE


def test_higher_net_fee_reason_code(e1_solution: VerifiedSolution) -> None:
    """AC-005."""
    explanations = {e.route_id: e for e in explain_routes(e1_solution)}

    assert ReasonCode.HIGHER_NET_FEE in explanations["RT-A"].reason_codes
    assert "net_fee_coefficient" in explanations["RT-A"].evidence
    # RT-B has the lower fee-revenue coefficient of the two routes sharing INV-1, so it never
    # "wins" the comparison -- it must not carry the code even though it also grew.
    route_b = explanations.get("RT-B")
    if route_b is not None:
        assert ReasonCode.HIGHER_NET_FEE not in route_b.reason_codes


def test_demand_cap_binding_reason_code(e1_solution: VerifiedSolution) -> None:
    """AC-006."""
    explanations = {e.route_id: e for e in explain_routes(e1_solution)}

    assert ReasonCode.DEMAND_CAP_BINDING in explanations["RT-A"].reason_codes
    assert explanations["RT-A"].evidence["demand_cap_slack_shares"] == pytest.approx(
        0.0, abs=DEFAULT_TOLERANCE
    )


def test_no_reason_codes_on_immaterial_change(pinned_route_solution: VerifiedSolution) -> None:
    """AC-007."""
    explanations = {e.route_id: e for e in explain_routes(pinned_route_solution)}

    assert "RT-PINNED" not in explanations
