# Tasks: Public API and CLI facade (T12)

- **Spec:** 0003-public-api-cli (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-04

> Ordered, testable units of work. Every task cites the requirement(s) it advances
> and carries a Definition of Done. No task without a requirement.

**Status note:** this entire file is a draft. Every task below is `todo`; none of T12 is built yet.
Do not treat any row here as evidence of completion.

## Definition of Done (applies to every task)

- Code matches `plan.md`; deviations noted there before merge, not silently.
- Tests exist and pass deterministically (`pytest tests/ -q`).
- No secrets, credentials, or private data introduced.
- CLI-facing code never lets a raw, unhandled traceback reach the user for a recognized exception
  class (NFR-002); every new module honors `ARC-002`'s "no `qr_haven` import" boundary (NFR-003).
- `specs/spec002/TRACEABILITY.md`'s `PLT-002` row and `docs/handoff.md`'s "Next priorities" section
  are updated alongside the change that closes them (T-013, T-014) — not deferred to a later commit.

## Task List

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-001 | Extract `formulation/context.py::build_context(request, config) -> BuildContext` from `compile_lp`'s current inline construction (move, don't rewrite, the `_compute_demand_caps`/`_group_by`-based block); refactor `compile_lp` to call it internally so its own public signature and behavior are unchanged. Update `tests/unit/reporting/conftest.py::_solve_and_verify` to call the new public function instead of reaching into `compile_lp`'s private helpers. | REQ-001 | todo | The one task in this spec that touches a file (`formulation/lp.py`'s internals, `formulation/context.py`) outside the "wrap, don't reinvent" set — flagged in `plan.md`/`spec.md` for explicit sign-off before starting. Existing `tests/unit/test_lp_compiler.py`/`test_solution_verifier.py`/`test_highs_backend.py`/`tests/golden/test_e1_scarce_name_allocation.py` must all still pass unchanged, proving `compile_lp`'s external behavior did not move. |
| T-002 | Add `services.py`: `OptimizationService`, `ExplanationService` (`runtime_checkable` `Protocol`s), `OptimizationExplanation` dataclass, `ExplanationServiceImpl.explain()`. | REQ-006, REQ-007, NFR-003 | todo | `ExplanationServiceImpl` reads only `OptimizationResult.allocations`; no solver/verifier call, no `VerifiedSolution` dependency. |
| T-003 | Add `facade.py::load_config(*, config_path=None, overrides=None) -> InventoryOptimizerConfig`, always applying `configs/default.yaml` as the `defaults` layer via `config.build_config`/`config.load_yaml_file`. | REQ-002 | todo | Deliberately the reduced signature from `plan.md`'s Trade-offs table, not §17.1's full five-axis illustrative call — see `spec.md` Non-Goals/Open Questions. |
| T-004 | Add `facade.py::InventoryOptimizer`: `__init__` (backend resolution via `_resolve_backend`, lazy `solvers.highs` import, `ConfigurationError` on an unregistered backend name) and `optimize()` (orchestrates `raise_if_invalid` → `build_context` → `compile_lp` → backend `.solve()` → `verify_solution` → `build_optimization_result`, computing `run_id`/`created_at`/`input_hash` itself and passing through an optional `platform` argument unchanged). | REQ-001, REQ-003, REQ-004, REQ-005, NFR-001, NFR-003 | todo | `_hash_request` reuses `config.hashing.canonical_json`, not a second hash implementation. |
| T-005 | Add `cli.py` `argparse` scaffold (`main(argv) -> int`, subparsers for all five verbs so `--help` lists them even before their handlers are real) and a working `_cmd_validate` (loads request JSON, calls `validation.validate_request`, prints every `ValidationIssue`, sets the exit code from `plan.md`'s table). | REQ-008, REQ-009, NFR-002 | todo | |
| T-006 | Add `cli.py::_cmd_optimize`: `load_config` + `InventoryOptimizer.optimize()`, JSON output to `--output`/stdout, exit-code mapping per `plan.md`'s table (success / feasible-limit / infeasible-unbounded / invalid-input / internal-error). | REQ-008, REQ-010, NFR-002, NFR-004 | todo | Must assert the written JSON parses under strict `json.loads` (rejects `NaN`/`Infinity`) — RISK-005. |
| T-007 | Add `cli.py::_cmd_components`: import `formulation.lp` for its registration side effect, print every `default_registry.manifest()` entry as JSON. | REQ-008, REQ-011 | todo | |
| T-008 | Add `cli.py::_cmd_doctor`: read-only checks (default config loads/hashes; configured solver backend importable/constructible; component registry non-empty post-import), each reported individually. | REQ-008, REQ-012, NFR-002 | todo | Must name the specific failing check, not a generic error (AC-014). |
| T-009 | Add `cli.py::_cmd_scenarios`: recognized subcommand, always exits non-zero with a message naming T13/T14 as the owning future work. | REQ-008, REQ-013 | todo | No `ScenarioService`/`ScenarioBatchRequest` dependency — this handler is standalone. |
| T-010 | Wire `[project.scripts]` (`inventory-optimizer = "inventory_optimizer.cli:main"`) into `pyproject.toml`; update `src/inventory_optimizer/__init__.py` to re-export `InventoryOptimizer`/`load_config`. | REQ-001, REQ-002, REQ-008 | todo | |
| T-011 | Unit tests: `tests/unit/test_facade.py`, `tests/unit/test_services.py`, reusing `e1_request`/`default_config`; cover AC-001 through AC-008. | REQ-001 through REQ-007, NFR-001, NFR-003 | todo | Includes the "no `qr_haven` in `sys.modules`" check (AC-006) and the `isinstance(..., OptimizationService)` structural check (AC-007). |
| T-012 | CLI tests: `tests/unit/test_cli.py` (in-process `cli.main(argv)` calls against `tmp_path` files) plus one `tests/golden/test_e1_cli_end_to_end.py` using `subprocess.run(["inventory-optimizer", ...])` against an installed console script; cover AC-009 through AC-015. | REQ-008 through REQ-013, NFR-002, NFR-004 | todo | The `subprocess` test is this task's evidence for `01_SPEC.md` §26's "end-to-end JSON test" and for `PLT-002`'s "end-to-end golden test" evidence column. |
| T-013 | Update `specs/spec002/TRACEABILITY.md`'s `PLT-002` row: add an evidence pointer to T-012's end-to-end test once it exists. Do **not** flip `PLT-002`'s status past `SPECIFIED` unilaterally — its `G2C` gate is a separate release approval this spec does not grant itself. | REQ-001 through REQ-013 | todo | Mirrors T11's own honest-completeness precedent (`LP-008` staying `SPECIFIED`) — do not overclaim here either. |
| T-014 | Update `docs/handoff.md`'s "Next priorities" section: mark T12 done with a pointer to this spec once implemented, and identify the next task after it (per `00_PLAN.md`'s Phase 2 / T13-T14). | REQ-001 through REQ-013 | todo | |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

Every acceptance criterion must be named by at least one test.

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | `test_facade.py::test_optimize_returns_verified_optimal_result` | todo |
| AC-002 | `test_facade.py::test_optimize_is_deterministic_modulo_identity_fields` | todo |
| AC-003 | `test_facade.py::test_load_config_matches_manual_build_config` | todo |
| AC-004 | `test_facade.py::test_input_hash_differs_on_request_change_matches_on_identical_request` | todo |
| AC-005 | `test_facade.py::test_unregistered_backend_raises_configuration_error` | todo |
| AC-006 | `test_facade.py::test_platform_context_passthrough_no_qr_haven_import` | todo |
| AC-007 | `test_services.py::test_inventory_optimizer_satisfies_optimization_service_protocol` | todo |
| AC-008 | `test_services.py::test_explanation_service_reads_result_without_resolving` | todo |
| AC-009 | `test_cli.py::test_help_lists_all_five_subcommands` | todo |
| AC-010 | `test_cli.py::test_validate_reports_every_issue_not_just_first` | todo |
| AC-011 | `test_e1_cli_end_to_end.py::test_optimize_twice_is_byte_identical_modulo_identity_fields` | todo |
| AC-012 | `test_cli.py::test_optimize_infeasible_request_has_distinct_exit_code` | todo |
| AC-013 | `test_cli.py::test_components_lists_known_registrations` | todo |
| AC-014 | `test_cli.py::test_doctor_reports_per_check_pass_fail` | todo |
| AC-015 | `test_cli.py::test_scenarios_subcommand_fails_fast_and_appears_in_help` | todo |

## Follow-ups

Tracked work intentionally deferred (no silent "temporary" shortcuts — P8).

- `ScenarioService`, `ScenarioBatchRequest`, `ScenarioComparison`, and `optimizer.run_scenarios(...)`
  wait for the scenario engine (T13-T14) to define their real shape; this spec's `scenarios` CLI
  subcommand is a placeholder name only, with no Protocol or type behind it.
- Full five-axis `load_config(environment=, desk=, formulation=, objective=, policy=)` profile
  resolution waits on `ObjectiveConfig`/policy config sections existing (no owning task yet) and on
  `CFG-004`/T35's desk-profile capability declarations.
- The QR Haven platform adapter (§17.4) and the platform-owned half of the invocation contract
  (§17.5: idempotency-key rejection enforcement, result caching, cancellation cooperation) are not
  this repository's code — see `spec.md` Non-Goals.
- A single-route `ExplanationService` lookup (versus only the whole-result aggregate) waits for a
  real caller need to surface, per `plan.md`'s Open Questions.
