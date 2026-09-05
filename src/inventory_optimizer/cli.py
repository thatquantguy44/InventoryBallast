"""``inventory-optimizer`` console script (T12; Section 17.3).

Mirrors the subparser/dispatch/``_cmd_*``/exit-code convention already established by
QuantSmith's own ``quantsmith-memory`` CLI (``quantsmith.pipelines.workflow_memory_cli``) rather
than inventing a new one -- one ``add_parser`` per verb, one ``_cmd_*`` handler per verb, a
``dispatch`` dict, and ``main(argv) -> int`` as the single entry point ``[project.scripts]`` needs.

Machine-readable output goes to ``--output``/stdout; diagnostics go to stderr; the exit code
distinguishes success, a feasible-limit result, an infeasible/unbounded model, an invalid-input
rejection, and an internal/solver error (NFR-002) -- never a raw, unhandled traceback for one of
those recognized failure classes.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from inventory_optimizer.domain.enums import SolverStatus
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.scenarios import Scenario
from inventory_optimizer.exceptions import (
    AttributionMismatchError,
    ConfigurationError,
    InputValidationError,
    RegistrationError,
    ScenarioApplicationError,
)
from inventory_optimizer.facade import InventoryOptimizer, load_config
from inventory_optimizer.scenarios.runner import run_scenarios
from inventory_optimizer.validation import validate_request

# Exit codes (Section 17.3; specs/0003-public-api-cli/plan.md's exit-code table).
EXIT_SUCCESS = 0
EXIT_INVALID_INPUT = 1
EXIT_INFEASIBLE_OR_UNBOUNDED = 2
EXIT_FEASIBLE_LIMIT = 3
EXIT_INTERNAL_ERROR = 4

_INFEASIBLE_STATUSES = frozenset(
    {SolverStatus.INFEASIBLE, SolverStatus.UNBOUNDED, SolverStatus.INFEASIBLE_OR_UNBOUNDED}
)


def _eprint(message: str) -> None:
    print(message, file=sys.stderr)


def _write_output(text: str, output_path: str | None) -> None:
    if output_path is None:
        print(text)
    else:
        Path(output_path).write_text(text + "\n", encoding="utf-8")


def _load_request(request_path: str) -> OptimizationRequest | None:
    """Returns ``None`` (after printing a diagnostic) on any load/parse/validation failure,
    rather than letting a raw traceback or a bare ``pydantic.ValidationError`` reach the user."""
    try:
        raw = json.loads(Path(request_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _eprint(f"invalid input: could not read/parse {request_path!r}: {exc}")
        return None
    try:
        return OptimizationRequest.model_validate(raw)
    except Exception as exc:  # pydantic.ValidationError: structural/type errors, not our own
        _eprint(f"invalid input: {request_path!r} is not a valid OptimizationRequest: {exc}")
        return None


def _cmd_validate(args: argparse.Namespace) -> int:
    request = _load_request(args.request)
    if request is None:
        return EXIT_INVALID_INPUT

    issues = validate_request(request)
    payload = [dataclasses.asdict(issue) for issue in issues]
    _write_output(json.dumps(payload, indent=2, sort_keys=True), args.output)
    return EXIT_INVALID_INPUT if issues else EXIT_SUCCESS


def _cmd_optimize(args: argparse.Namespace) -> int:
    request = _load_request(args.request)
    if request is None:
        return EXIT_INVALID_INPUT

    try:
        config = load_config(config_path=Path(args.config) if args.config else None)
        optimizer = InventoryOptimizer(config=config)
        result = optimizer.optimize(request)
    except InputValidationError as exc:
        _eprint(f"invalid input: {exc}")
        return EXIT_INVALID_INPUT
    except ConfigurationError as exc:
        _eprint(f"configuration error: {exc}")
        return EXIT_INTERNAL_ERROR
    except (RegistrationError, AttributionMismatchError) as exc:
        _eprint(f"internal error: {exc}")
        return EXIT_INTERNAL_ERROR

    _write_output(result.model_dump_json(indent=2), args.output)

    if result.status in _INFEASIBLE_STATUSES:
        return EXIT_INFEASIBLE_OR_UNBOUNDED
    if not result.verification.passed:
        return EXIT_INTERNAL_ERROR
    if result.status is SolverStatus.FEASIBLE_LIMIT:
        return EXIT_FEASIBLE_LIMIT
    if result.status is SolverStatus.OPTIMAL:
        return EXIT_SUCCESS
    return EXIT_INTERNAL_ERROR


def _cmd_components(args: argparse.Namespace) -> int:
    # Import for its component-registration side effect (Section 15: registration happens at
    # module import) so the listing reflects what a real compile_lp() call actually uses.
    import inventory_optimizer.formulation.lp  # noqa: F401
    from inventory_optimizer.components.registry import default_registry

    manifest = [
        {
            "kind": registration.kind.value,
            "name": registration.name,
            "version": registration.version,
        }
        for registration in default_registry.manifest()
    ]
    _write_output(json.dumps(manifest, indent=2, sort_keys=True), args.output)
    return EXIT_SUCCESS


def _cmd_doctor(args: argparse.Namespace) -> int:
    checks: list[dict[str, object]] = []
    all_passed = True

    try:
        config = load_config()
        from inventory_optimizer.config.hashing import config_hash

        config_hash(config)
        checks.append({"check": "default_config_loads_and_hashes", "passed": True})
    except Exception as exc:  # doctor reports every failure as a check result, never crashes
        checks.append(
            {"check": "default_config_loads_and_hashes", "passed": False, "detail": str(exc)}
        )
        all_passed = False
        config = None

    if config is not None:
        try:
            InventoryOptimizer(config=config)
            checks.append({"check": "solver_backend_constructible", "passed": True})
        except ConfigurationError as exc:
            checks.append(
                {"check": "solver_backend_constructible", "passed": False, "detail": str(exc)}
            )
            all_passed = False
    else:
        checks.append(
            {
                "check": "solver_backend_constructible",
                "passed": False,
                "detail": "skipped: no config",
            }
        )
        all_passed = False

    try:
        import inventory_optimizer.formulation.lp  # noqa: F401
        from inventory_optimizer.components.registry import default_registry

        registered = len(default_registry.manifest())
        passed = registered > 0
        checks.append(
            {
                "check": "component_registry_non_empty",
                "passed": passed,
                "detail": f"{registered} registered",
            }
        )
        all_passed = all_passed and passed
    except Exception as exc:
        checks.append(
            {"check": "component_registry_non_empty", "passed": False, "detail": str(exc)}
        )
        all_passed = False

    _write_output(json.dumps(checks, indent=2, sort_keys=True), args.output)
    return EXIT_SUCCESS if all_passed else EXIT_INTERNAL_ERROR


def _load_scenarios(scenario_path: str) -> tuple[tuple[Scenario, ...], bool] | None:
    """Returns ``(scenarios, was_single_object)`` or ``None`` (after printing a diagnostic) on
    any load/parse/validation failure. A scenario file is either one ``Scenario`` object or a
    JSON array of them (REQ-010)."""
    try:
        raw = json.loads(Path(scenario_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _eprint(f"invalid input: could not read/parse {scenario_path!r}: {exc}")
        return None
    try:
        if isinstance(raw, list):
            return tuple(Scenario.model_validate(item) for item in raw), False
        return (Scenario.model_validate(raw),), True
    except Exception as exc:  # pydantic.ValidationError: structural/type errors, not our own
        _eprint(f"invalid input: {scenario_path!r} is not a valid Scenario (or list of): {exc}")
        return None


def _cmd_scenarios(args: argparse.Namespace) -> int:
    request = _load_request(args.request)
    if request is None:
        return EXIT_INVALID_INPUT
    loaded = _load_scenarios(args.scenario)
    if loaded is None:
        return EXIT_INVALID_INPUT
    scenarios, was_single = loaded

    try:
        config = load_config(config_path=Path(args.config) if args.config else None)
        optimizer = InventoryOptimizer(config=config)
        baseline_result = optimizer.optimize(request)
        comparisons = run_scenarios(request, baseline_result, scenarios, optimizer)
    except InputValidationError as exc:
        _eprint(f"invalid input: {exc}")
        return EXIT_INVALID_INPUT
    except ScenarioApplicationError as exc:
        _eprint(f"invalid input: {exc}")
        return EXIT_INVALID_INPUT
    except ConfigurationError as exc:
        _eprint(f"configuration error: {exc}")
        return EXIT_INTERNAL_ERROR
    except (RegistrationError, AttributionMismatchError) as exc:
        _eprint(f"internal error: {exc}")
        return EXIT_INTERNAL_ERROR

    if was_single:
        payload = comparisons[0].model_dump_json(indent=2)
    else:
        payload = json.dumps([c.model_dump(mode="json") for c in comparisons], indent=2)
    _write_output(payload, args.output)

    if any(c.status in _INFEASIBLE_STATUSES for c in comparisons):
        return EXIT_INFEASIBLE_OR_UNBOUNDED
    if any(not c.verification_passed for c in comparisons):
        return EXIT_INTERNAL_ERROR
    return EXIT_SUCCESS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="inventory-optimizer")
    sub = parser.add_subparsers(dest="command")

    p_validate = sub.add_parser("validate", help="Validate an OptimizationRequest JSON file.")
    p_validate.add_argument("--request", required=True, help="Path to an OptimizationRequest JSON.")
    p_validate.add_argument("--output", help="Write JSON output here instead of stdout.")

    p_optimize = sub.add_parser("optimize", help="Solve a request and report the result.")
    p_optimize.add_argument("--request", required=True, help="Path to an OptimizationRequest JSON.")
    p_optimize.add_argument("--config", help="Path to a YAML config file (the 'run' layer).")
    p_optimize.add_argument("--output", help="Write the OptimizationResult JSON here, not stdout.")

    p_scenarios = sub.add_parser("scenarios", help="Run one or more scenarios against a request.")
    p_scenarios.add_argument("--request", required=True, help="Path to the baseline request JSON.")
    p_scenarios.add_argument(
        "--scenario", required=True, help="Path to a Scenario JSON file (object or array)."
    )
    p_scenarios.add_argument("--config", help="Path to a YAML config file (the 'run' layer).")
    p_scenarios.add_argument("--output", help="Write the comparison JSON here, not stdout.")

    p_components = sub.add_parser("components", help="List every registered component.")
    p_components.add_argument("--output", help="Write JSON output here instead of stdout.")

    p_doctor = sub.add_parser("doctor", help="Run read-only environment/config self-checks.")
    p_doctor.add_argument("--output", help="Write JSON output here instead of stdout.")

    return parser


_DISPATCH = {
    "validate": _cmd_validate,
    "optimize": _cmd_optimize,
    "scenarios": _cmd_scenarios,
    "components": _cmd_components,
    "doctor": _cmd_doctor,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = _DISPATCH.get(args.command)
    if handler is None:
        parser.print_help()
        return EXIT_INVALID_INPUT
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
