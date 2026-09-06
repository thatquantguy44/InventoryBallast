"""Result assembly tests (T11; Section 18.1; VER-006).

AC-004: every one of the fifteen Section 18.1 sections is present on the assembled
``OptimizationResult`` and none raises ``NotImplementedError`` -- the sections with no implemented
upstream data source yet (Schedules, Collateral, Sources) are explicitly ``None``, not fabricated.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from inventory_optimizer.domain.results import OptimizationResult
from inventory_optimizer.reporting.result_builder import build_optimization_result
from inventory_optimizer.reporting.types import VerifiedSolution


def test_all_sections_present(e1_solution: VerifiedSolution) -> None:
    """AC-004."""
    result = build_optimization_result(
        e1_solution,
        run_id="run-test-1",
        created_at=datetime(2026, 9, 4, tzinfo=UTC),
        config_hash="cfg-hash-test",
        input_hash="input-hash-test",
    )

    # Identity
    assert result.request_id == "REQ-E1"
    assert result.run_id == "run-test-1"
    assert result.config_hash == "cfg-hash-test"
    assert result.input_hash == "input-hash-test"
    assert result.package_version

    # Status
    assert result.status is not None

    # The remaining thirteen Section 18.1 sections
    assert len(result.allocations) == 2
    assert len(result.balances) == 1
    assert result.economics.total_value_usd == pytest.approx(result.economics.total_delta_usd)
    assert len(result.demand) == 2
    assert result.schedules is None
    assert result.collateral is None
    assert result.desk is not None
    assert result.sources is None
    assert len(result.constraints) > 0
    assert result.solver.backend_name == "highs"
    assert result.verification.passed is True
    assert isinstance(result.warnings, tuple)
    assert result.platform is None


def test_result_is_deterministic_given_the_same_inputs(e1_solution: VerifiedSolution) -> None:
    """NFR-004: pure assembly, no hidden clock/random state."""
    created_at = datetime(2026, 9, 4, tzinfo=UTC)

    first = build_optimization_result(
        e1_solution,
        run_id="run-test-1",
        created_at=created_at,
        config_hash="cfg-hash-test",
        input_hash="input-hash-test",
    )
    second = build_optimization_result(
        e1_solution,
        run_id="run-test-1",
        created_at=created_at,
        config_hash="cfg-hash-test",
        input_hash="input-hash-test",
    )

    assert first == second


def test_result_round_trips_through_its_own_json(e1_solution: VerifiedSolution) -> None:
    """Regression (specs/0008-tabular-result-output/): JSON has no infinity literal, so Pydantic
    serializes an unbounded ``ConstraintActivity.lower`` (E1's demand_cap rows are one-sided,
    ``-inf``) as ``null``. Before the ``UnboundedBelow``/``UnboundedAbove`` validators, reading
    that JSON back raised -- meaning `optimize --output result.json` had always written a file the
    package itself could not parse. Nothing exercised this until the `tables` CLI subcommand read
    a result back for the first time."""
    result = build_optimization_result(
        e1_solution,
        run_id="run-test-round-trip",
        created_at=datetime(2026, 9, 4, tzinfo=UTC),
        config_hash="cfg-hash-test",
        input_hash="input-hash-test",
    )
    demand_cap_rows = [c for c in result.constraints if c.row.kind == "demand_cap"]
    assert demand_cap_rows and any(math.isinf(c.lower) for c in demand_cap_rows)

    restored = OptimizationResult.model_validate_json(result.model_dump_json())

    assert restored == result
    assert restored.model_dump_json() == result.model_dump_json()
