# Tasks: Scenario engine and basic stress testing (T13-T14)

- **Spec:** 0004-scenario-engine (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-05

> Ordered, testable units of work. Every task cites the requirement(s) it advances
> and carries a Definition of Done. No task without a requirement.

**Status:** implemented (2026-09-05). All 10 ACs pass; 141/141 tests pass (`pytest tests/ -q`);
ruff clean. E2 and E3 (`EXAMPLES.md`) both reproduced exactly with no changes needed to
`reporting/`, `formulation/`, or `validation/`. See `plan.md`'s "Deviations Discovered During
Implementation" for the two real refinements found while building this (`apply_scenario`'s return
type, `InventoryOptimizer.config`).

## Definition of Done (applies to every task)

- Code matches `plan.md`; deviations noted there before merge, not silently.
- Tests exist and pass deterministically (`pytest tests/ -q`).
- No secrets, credentials, or private data introduced.
- A scenario-modified `OptimizationRequest` is never round-tripped through `model_validate`/
  `model_dump_json`-then-reload anywhere in `scenarios/`/`cli.py` (NFR-003).
- `specs/spec002/TRACEABILITY.md`'s `SCN-001`-`SCN-003` rows and `docs/handoff.md`'s "Next
  priorities" section are updated alongside the change that closes them (T-009, T-010).

## Task List

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-001 | Add `domain/enums.py::TradeEventType`; add `domain/scenarios.py`: `TradeEvent`, `RateShock`, `DemandShock`, `Scenario`. | REQ-001 | done | `TradeEvent`'s model_validator enforces `inventory_id` xor `route_id` per event type; `Scenario`'s enforces unique `trade_events` event IDs. |
| T-002 | Add `scenarios/apply.py::apply_scenario`: timing-gated, deterministically-sorted trade-event application (all seven types per `plan.md`'s table), rate/demand shock application, the two rejection checks (REQ-003/004 via a new `exceptions.ScenarioApplicationError`). | REQ-002, REQ-003, REQ-004, REQ-005, NFR-001, NFR-003 | done | Never calls `.model_validate()`/`model_dump_json()` on the scenario-modified request or any nested record — only `.model_copy()` (the load-bearing design decision `plan.md` explains). |
| T-003 | Add `scenarios/runner.py::run_scenario`/`run_scenarios`: re-validate (`raise_if_invalid`), re-solve via `InventoryOptimizer.optimize()`, delegate to `build_scenario_comparison`. | REQ-006, REQ-008, NFR-002, NFR-003 | done | `run_scenarios` is literally `tuple(run_scenario(...) for s in scenarios)` — batch/isolated equivalence by construction, not by a separate equivalence-preserving code path. |
| T-004 | Add `domain/scenario_results.py`: `RouteAllocationDelta`, `InventoryBalanceDelta`, `ScenarioComparison`. Add `scenarios/compare.py::build_scenario_comparison`. | REQ-007 | done | Reuses `components.objective_terms.fee_revenue.fee_revenue_coefficient` for the `TRADE_REDUCED_SUPPLY` per-route revenue estimate — no second coefficient definition. |
| T-005 | Add `services.py::ScenarioService` (`runtime_checkable` Protocol) and `ScenarioServiceImpl` composing `apply_scenario`/`run_scenarios`. | REQ-009 | done | Mirrors `OptimizationService`/`InventoryOptimizer`'s existing structural-typing pattern from T12. |
| T-006 | Implement `cli.py::_cmd_scenarios` for real: `--request`, `--scenario` (one `Scenario` or a JSON array), `--config`, `--output`; exit code distinguishes all-feasible / some-infeasible / invalid-input. | REQ-010 | done | Loads the baseline request and scenario(s) from JSON, but keeps the scenario-modified request in-process (never re-serialized) before calling `optimizer.optimize()` — see NFR-003. |
| T-007 | Add `scenarios/runner.py::run_stress_test` and `domain/scenario_results.py::StressScenarioOutcome`/`StressTestReport`. | REQ-011 | done | Library function only this pass — no CLI subcommand (`plan.md`'s Open Questions). |
| T-008 | Tests: `tests/unit/test_scenarios_apply.py`, `test_scenarios_runner.py`, `tests/golden/test_e2_rate_shock_scenario.py`, `test_e3_sale_and_recall_scenario.py`; extend `tests/unit/test_services.py`, `test_cli.py`. Cover AC-001 through AC-010. | REQ-001 through REQ-011 | done | See Test Coverage Map below. |
| T-009 | Update `specs/spec002/TRACEABILITY.md`: `SCN-001`, `SCN-002`, `SCN-003` rows `SPECIFIED` → `IMPLEMENTED` with evidence pointers to T-008's tests. `SCN-004` stays `SPECIFIED` (tagged `T40`). | REQ-001 through REQ-011 | done | |
| T-010 | Update `docs/handoff.md`: mark T13-T14 done with a pointer to this spec; identify the next task (Phase 3, MIP business rules, per `00_PLAN.md`). | REQ-001 through REQ-011 | done | |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | `test_e2_rate_shock_scenario.py::test_rate_shock_reproduces_e2_demand_cap_and_reason_code` | done |
| AC-002 | `test_e2_rate_shock_scenario.py::test_baseline_request_unchanged_after_scenario` | done |
| AC-003 | `test_e3_sale_and_recall_scenario.py::test_feasible_sale_redistributes_allocation` | done |
| AC-004 | `test_e3_sale_and_recall_scenario.py::test_infeasible_sale_with_hard_minimum_conflict` | done |
| AC-005 | `test_scenarios_apply.py::test_conflicting_return_events_are_rejected` | done |
| AC-006 | `test_scenarios_apply.py::test_oversized_sell_is_rejected` | done |
| AC-007 | `test_scenarios_runner.py::test_batch_matches_isolated_runs` | done |
| AC-008 | `test_services.py::test_scenario_service_impl_satisfies_protocol` | done |
| AC-009 | `test_cli.py::test_scenarios_single_and_batch_files` | done |
| AC-010 | `test_scenarios_runner.py::test_stress_test_report_counts_and_worst_case` | done |

## Follow-ups

Tracked work intentionally deferred (no silent "temporary" shortcuts — P8).

- `schedule_overlays`, `collateral_shocks`, `desk_events`, `InventoryShock`, `PolicyOverride` wait
  on their owning subsystems (T29, T30-T32, T35-T39) or a concrete worked example — see `spec.md`
  Non-Goals.
- Schedule/calendar-aware settlement timing (beyond plain `effective_date <= request.effective_date`
  comparison) waits on `T21`.
- A CLI `stress` subcommand (or a `--stress` flag on `scenarios`) waits on a real workflow asking
  for one — `run_stress_test` is a library function only this pass.
- Warm-start/shared-model reuse for `run_scenarios` (performance, not correctness) is untracked by
  any task yet.
- A full per-route, per-objective-component P&L attribution (beyond the fee-revenue-only estimate
  `ScenarioComparison` computes for `TRADE_REDUCED_SUPPLY` routes) waits on a real need, per T11's
  own precedent of not extending `EconomicsSummary` speculatively.
