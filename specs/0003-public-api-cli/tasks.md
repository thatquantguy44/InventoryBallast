# Tasks: Public API and CLI facade (T12)

- **Spec:** 0003-public-api-cli (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-05

> Ordered, testable units of work. Every task cites the requirement(s) it advances
> and carries a Definition of Done. No task without a requirement.

**Status:** implemented (2026-09-05). All 15 ACs pass; 125/125 tests pass (`pytest tests/ -q`);
ruff clean. Two real deviations surfaced during implementation and were fixed rather than worked
around -- see `plan.md`'s "Deviations Discovered During Implementation" section.

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
| T-001 | Extract `formulation/context.py::build_context(request, config) -> BuildContext` from `compile_lp`'s current inline construction (move, don't rewrite, the `_compute_demand_caps`/`_group_by`-based block); refactor `compile_lp` to call it internally so its own public signature and behavior are unchanged. Update `tests/unit/reporting/conftest.py::_solve_and_verify` to call the new public function instead of reaching into `compile_lp`'s private helpers. | REQ-001 | done | Confirmed behavior-preserving: all 107 pre-existing tests (`test_lp_compiler.py`, `test_solution_verifier.py`, `test_highs_backend.py`, `tests/golden/test_e1_scarce_name_allocation.py`, the T11 reporting suite) still pass unchanged. |
| T-002 | Add `services.py`: `OptimizationService`, `ExplanationService` (`runtime_checkable` `Protocol`s), `OptimizationExplanation` dataclass, `ExplanationServiceImpl.explain()`. | REQ-006, REQ-007, NFR-003 | done | Also added `RouteExplanationView` (not named in `plan.md`'s sketch) as the per-route element of `OptimizationExplanation.routes_with_reasons` — a small, obviously-needed supporting type, not a scope change. |
| T-003 | Add `facade.py::load_config(*, config_path=None, overrides=None) -> InventoryOptimizerConfig`, always applying `configs/default.yaml` as the `defaults` layer via `config.build_config`/`config.load_yaml_file`. | REQ-002 | done | `_PACKAGE_DEFAULT_YAML_PATH` resolves relative to `facade.py`'s own location (`Path(__file__).resolve().parents[2] / "configs" / "default.yaml"`), matching `tests/conftest.py`'s existing convention — works for the editable-install workflow `docs/handoff.md` documents; a real (non-editable) wheel distribution is out of scope, noted but not solved here. |
| T-004 | Add `facade.py::InventoryOptimizer`: `__init__` (backend resolution via `_resolve_backend`, lazy `solvers.highs` import, `ConfigurationError` on an unregistered backend name) and `optimize()` (orchestrates `raise_if_invalid` → `build_context` → `compile_lp` → backend `.solve()` → `verify_solution` → `build_optimization_result`, computing `run_id`/`created_at`/`input_hash` itself and passing through an optional `platform` argument unchanged). | REQ-001, REQ-003, REQ-004, REQ-005, NFR-001, NFR-003 | done | Surfaced a real, pre-existing bug while implementing `_hash_request`: `OptimizationRequest.model_dump(mode="json")` raised `PydanticSerializationError` on its own `config_overrides`/`metadata` defaults (`MappingProxyType({})` has no pydantic-core serializer). Fixed with `@field_serializer` in `domain/requests.py` (and, for the same reason, `domain/results.py`'s `AllocationRecord.explanation_evidence`, a T11 field with the identical default) — see `plan.md`'s Deviations section. |
| T-005 | Add `cli.py` `argparse` scaffold (`main(argv) -> int`, subparsers for all five verbs so `--help` lists them even before their handlers are real) and a working `_cmd_validate` (loads request JSON, calls `validation.validate_request`, prints every `ValidationIssue`, sets the exit code from `plan.md`'s table). | REQ-008, REQ-009, NFR-002 | done | |
| T-006 | Add `cli.py::_cmd_optimize`: `load_config` + `InventoryOptimizer.optimize()`, JSON output to `--output`/stdout, exit-code mapping per `plan.md`'s table (success / feasible-limit / infeasible-unbounded / invalid-input / internal-error). | REQ-008, REQ-010, NFR-002, NFR-004 | done | `test_optimize_is_deterministic_modulo_identity_fields`/`test_optimize_twice_is_identical_modulo_identity_fields` both failed on first run with `solver.runtime_seconds` as the only differing field — corrected `spec.md`'s NFR-001/NFR-004/AC-002/AC-011 wording rather than the code (the non-determinism is real and expected: wall-clock solve time). |
| T-007 | Add `cli.py::_cmd_components`: import `formulation.lp` for its registration side effect, print every `default_registry.manifest()` entry as JSON. | REQ-008, REQ-011 | done | Projects only `{kind, name, version}` per entry — `ComponentRegistration.component_class` is a raw Python class and not JSON-serializable, so the full dataclass is never dumped directly. |
| T-008 | Add `cli.py::_cmd_doctor`: read-only checks (default config loads/hashes; configured solver backend importable/constructible; component registry non-empty post-import), each reported individually. | REQ-008, REQ-012, NFR-002 | done | |
| T-009 | Add `cli.py::_cmd_scenarios`: recognized subcommand, always exits non-zero with a message naming T13/T14 as the owning future work. | REQ-008, REQ-013 | done | |
| T-010 | Wire `[project.scripts]` (`inventory-optimizer = "inventory_optimizer.cli:main"`) into `pyproject.toml`; update `src/inventory_optimizer/__init__.py` to re-export `InventoryOptimizer`/`load_config`. | REQ-001, REQ-002, REQ-008 | done | Verified via `pip install -e . --no-deps` + `inventory-optimizer --help` against the real installed script, not just the in-process entry point. |
| T-011 | Unit tests: `tests/unit/test_facade.py`, `tests/unit/test_services.py`, reusing `e1_request`/`default_config`; cover AC-001 through AC-008. | REQ-001 through REQ-007, NFR-001, NFR-003 | done | AC-007's test asserts `InventoryOptimizer.__bases__ == (object,)` rather than `not issubclass(InventoryOptimizer, OptimizationService)` — a `runtime_checkable` Protocol structurally satisfies `issubclass` too whenever the method shape matches, which is expected Protocol behavior, not something to disprove. |
| T-012 | CLI tests: `tests/unit/test_cli.py` (in-process `cli.main(argv)` calls against `tmp_path` files) plus one `tests/golden/test_e1_cli_end_to_end.py` using `subprocess.run` against the installed console script (located via `Path(sys.executable).parent / "inventory-optimizer"`, skipped if not installed); cover AC-009 through AC-015. | REQ-008 through REQ-013, NFR-002, NFR-004 | done | AC-010's fixture changes `on_loan_shares` *and* `available_to_lend_shares` together (not `on_loan_shares` alone) so `SecurityInventory`'s own single-record balance identity still holds when the request round-trips through JSON (`model_validate` re-runs every field validator; an in-memory `model_copy` does not) — only the cross-record `ON_LOAN_RECONCILIATION_FAILED` check should fail, not construction itself. |
| T-013 | Update `specs/spec002/TRACEABILITY.md`'s `PLT-002` row: add an evidence pointer to T-012's end-to-end test once it exists. Do **not** flip `PLT-002`'s status past `SPECIFIED` unilaterally — its `G2C` gate is a separate release approval this spec does not grant itself. | REQ-001 through REQ-013 | done | Confirmed `G2C` (`specs/spec002/ROADMAPS.md`) is a cross-cutting platform-ownership gate shared with `PLT-001`, `PLT-003`-`PLT-006` (all T17/T34-owned, none of which this repo builds) — `SPECIFIED` is correct to keep, not just cautious. |
| T-014 | Update `docs/handoff.md`'s "Next priorities" section: mark T12 done with a pointer to this spec once implemented, and identify the next task after it (per `00_PLAN.md`'s Phase 2 / T13-T14). | REQ-001 through REQ-013 | done | |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

Every acceptance criterion must be named by at least one test.

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | `test_facade.py::test_optimize_returns_verified_optimal_result` | done |
| AC-002 | `test_facade.py::test_optimize_is_deterministic_modulo_identity_fields` | done |
| AC-003 | `test_facade.py::test_load_config_matches_manual_build_config` | done |
| AC-004 | `test_facade.py::test_input_hash_differs_on_request_change_matches_on_identical_request` | done |
| AC-005 | `test_facade.py::test_unregistered_backend_raises_configuration_error` | done |
| AC-006 | `test_facade.py::test_platform_context_passthrough_no_qr_haven_import` | done |
| AC-007 | `test_services.py::test_inventory_optimizer_satisfies_optimization_service_protocol` | done |
| AC-008 | `test_services.py::test_explanation_service_reads_result_without_resolving` | done |
| AC-009 | `test_cli.py::test_help_lists_all_five_subcommands` | done |
| AC-010 | `test_cli.py::test_validate_reports_every_issue_not_just_first` | done |
| AC-011 | `test_cli.py::test_optimize_twice_is_identical_modulo_identity_fields` | done |
| AC-012 | `test_cli.py::test_optimize_infeasible_request_has_distinct_exit_code` | done |
| AC-013 | `test_cli.py::test_components_lists_known_registrations` | done |
| AC-014 | `test_cli.py::test_doctor_reports_per_check_pass_fail` + `test_doctor_names_solver_backend_failure_specifically` | done |
| AC-015 | Superseded 2026-09-05 — see `spec.md`'s AC-015 note; `test_cli.py::test_scenarios_subcommand_appears_in_help` covers what's still true | superseded |

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
- Packaging `configs/default.yaml` as real installed package data (for a non-editable wheel install,
  not just the editable-install workflow this repo documents) is untracked by any task yet.
