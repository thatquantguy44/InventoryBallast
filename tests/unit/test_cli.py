"""CLI tests (T12; Section 17.3; specs/0003-public-api-cli/).

In-process ``cli.main(argv)`` calls against ``tmp_path``-written request/config files, asserting on
``capsys`` output and the returned exit code -- faster and more debuggable than shelling out, while
still exercising the real ``argparse`` wiring. ``tests/golden/test_e1_cli_end_to_end.py`` covers the
one thing this cannot: a real installed console script via ``subprocess``.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from inventory_optimizer.cli import (
    EXIT_INFEASIBLE_OR_UNBOUNDED,
    EXIT_INTERNAL_ERROR,
    EXIT_INVALID_INPUT,
    EXIT_SUCCESS,
    main,
)
from inventory_optimizer.exceptions import ConfigurationError


def _write_request(path: Path, request) -> None:
    path.write_text(request.model_dump_json())


def test_help_lists_all_five_subcommands(capsys) -> None:
    """AC-009."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == EXIT_SUCCESS
    output = capsys.readouterr().out
    for verb in ("validate", "optimize", "scenarios", "components", "doctor"):
        assert verb in output


def test_validate_reports_every_issue_not_just_first(tmp_path, e1_request, capsys) -> None:
    """AC-010: a stale `as_of` and a separately-broken on-loan reconciliation, both reported.
    ``on_loan_shares``/``available_to_lend_shares`` are changed together so the record's own
    single-record balance identity still holds (only the cross-record route-sum check breaks) --
    a request loaded from JSON re-validates every field, unlike an in-memory ``model_copy``."""
    stale_and_broken_inventory = e1_request.inventory[0].model_copy(
        update={
            "as_of": e1_request.as_of - timedelta(hours=48),
            "on_loan_shares": 20.0,
            "available_to_lend_shares": 80.0,
        }
    )
    broken_request = e1_request.model_copy(
        update={"inventory": (stale_and_broken_inventory,)}
    )
    request_path = tmp_path / "request.json"
    _write_request(request_path, broken_request)

    exit_code = main(["validate", "--request", str(request_path)])
    issues = json.loads(capsys.readouterr().out)

    assert exit_code == EXIT_INVALID_INPUT
    codes = {issue["code"] for issue in issues}
    assert "STALE_OR_FUTURE_AS_OF" in codes
    assert "ON_LOAN_RECONCILIATION_FAILED" in codes


def test_validate_malformed_json_is_invalid_input_not_a_traceback(tmp_path, capsys) -> None:
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not valid json")

    exit_code = main(["validate", "--request", str(bad_path)])

    assert exit_code == EXIT_INVALID_INPUT
    assert capsys.readouterr().err  # a diagnostic was printed, not a raw traceback


def test_optimize_twice_is_identical_modulo_identity_fields(tmp_path, e1_request, capsys) -> None:
    """AC-011."""
    request_path = tmp_path / "request.json"
    _write_request(request_path, e1_request)
    config_path = tmp_path / "run.yaml"
    config_path.write_text("{}\n")

    first_output = tmp_path / "result1.json"
    second_output = tmp_path / "result2.json"

    base_args = ["optimize", "--request", str(request_path), "--config", str(config_path)]
    exit_1 = main([*base_args, "--output", str(first_output)])
    exit_2 = main([*base_args, "--output", str(second_output)])

    assert exit_1 == EXIT_SUCCESS
    assert exit_2 == EXIT_SUCCESS

    first = json.loads(first_output.read_text())
    second = json.loads(second_output.read_text())
    assert first["verification"]["passed"] is True

    for payload in (first, second):
        del payload["run_id"]
        del payload["created_at"]
        del payload["solver"]["runtime_seconds"]
    assert first == second


def test_optimize_infeasible_request_has_distinct_exit_code(
    tmp_path, inventory_factory, route_factory, demand_factory
) -> None:
    """AC-012: a route pinned at a quantity its own demand-group cap forbids -- infeasible by
    conflicting bounds, not by any validate()-caught issue (reconciliation/freshness both pass)."""
    from datetime import UTC, date, datetime

    from inventory_optimizer.domain.requests import OptimizationRequest

    as_of = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    inventory = inventory_factory(
        total_lendable_shares=20.0, on_loan_shares=8.0, available_to_lend_shares=12.0
    )
    pinned_route = route_factory(
        "RT-PINNED",
        "DG-PINNED",
        fee_rate=0.02,
        current_quantity_shares=8.0,
        hard_minimum_quantity_shares=8.0,
        maximum_quantity_shares=8.0,
    )
    demand = demand_factory(
        "DG-PINNED", "BORROWER-RT-PINNED", fee_rate=0.02, reference_quantity_shares=5.0
    )
    request = OptimizationRequest(
        request_id="REQ-INFEASIBLE",
        as_of=as_of,
        effective_date=date(2026, 9, 3),
        inventory=(inventory,),
        routes=(pinned_route,),
        demand=(demand,),
    )
    request_path = tmp_path / "request.json"
    _write_request(request_path, request)

    exit_code = main(["optimize", "--request", str(request_path)])

    assert exit_code == EXIT_INFEASIBLE_OR_UNBOUNDED
    assert exit_code not in (EXIT_SUCCESS, EXIT_INVALID_INPUT)


def test_components_lists_known_registrations(capsys) -> None:
    """AC-013."""
    exit_code = main(["components"])
    manifest = json.loads(capsys.readouterr().out)

    assert exit_code == EXIT_SUCCESS
    names = {entry["name"] for entry in manifest}
    assert {"fee_revenue", "transition_cost", "inventory_balance"} <= names


def test_doctor_reports_per_check_pass_fail(capsys) -> None:
    """AC-014 (positive case)."""
    exit_code = main(["doctor"])
    checks = json.loads(capsys.readouterr().out)

    assert exit_code == EXIT_SUCCESS
    assert checks
    assert all(check["passed"] for check in checks)


def test_doctor_names_solver_backend_failure_specifically(monkeypatch, capsys) -> None:
    """AC-014 (negative case): the solver-backend check is named specifically, not a generic
    traceback, when the backend cannot be constructed."""
    import inventory_optimizer.facade as facade_module

    def _broken_resolve_backend(solver_config):
        raise ConfigurationError(
            "solver backend 'highs' requires the 'highs' extra (pip install -e '.[highs]')"
        )

    monkeypatch.setattr(facade_module, "_resolve_backend", _broken_resolve_backend)

    exit_code = main(["doctor"])
    checks = json.loads(capsys.readouterr().out)

    assert exit_code == EXIT_INTERNAL_ERROR
    solver_check = next(c for c in checks if c["check"] == "solver_backend_constructible")
    assert solver_check["passed"] is False
    assert "highs" in solver_check["detail"]


def test_scenarios_subcommand_fails_fast_and_appears_in_help(capsys) -> None:
    """AC-015."""
    exit_code = main(["scenarios"])
    err = capsys.readouterr().err

    assert exit_code == EXIT_INTERNAL_ERROR
    assert "T13" in err or "T14" in err

    with pytest.raises(SystemExit):
        main(["--help"])
    assert "scenarios" in capsys.readouterr().out
