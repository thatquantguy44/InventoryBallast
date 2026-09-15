# Tasks: Bloomberg data foundation (Realism release R0)

- **Spec:** 0011-bloomberg-data-foundation (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-14

> Ordered, testable units of work. Every task cites the requirement(s) it advances and carries a
> Definition of Done. No task without a requirement.

**Status note:** `spec.md` is **Approved** (owner, 2026-09-14): synthetic-only adapter confirmed;
"new route" = `current_quantity_shares == 0` adopted as a V0 default despite being flagged
uncertain (RISK-003 tracks revisiting it); REQ-012/REQ-013 are non-blocking warnings, not hard
failures. **T-001 through T-014 are all `done` (2026-09-14):** every requirement/AC in `spec.md`
has a passing test; 326 passed (up from 277 pre-this-spec), 4 slow-marked deselected, zero
regressions; `pytest tests/ -m slow -q` gives 4 passed unchanged. One scope addition beyond
`plan.md`'s original sketch, recorded here rather than silently: REQ-013's calendar check is also
wired into `scenarios.apply.apply_scenario` (not only `settlement.project`/
`formulation.multi_period`), since `spec.md`'s own AC-006 explicitly exercises a scenario trade
event's settlement date — `plan.md`'s Module layout section did not originally list
`scenarios/apply.py`, but the wiring is the same optional-keyword, warnings-only pattern used
everywhere else in this spec.

## Definition of Done (applies to every task)

- Code matches `plan.md`; deviations noted there before merge, not silently.
- Tests exist and pass deterministically (`pytest tests/ -q`).
- No secrets, credentials, or private data introduced; no fixture is a captured real Bloomberg
  response (NFR-004).
- Every existing test continues to pass unchanged (NFR-001) — run the full suite after every task,
  not just at the end.
- No Bloomberg field mnemonic appears outside `adapters/bloomberg/` (NFR-002).
- `specs/engine_spec/TRACEABILITY.md` (`DAT-001`-`DAT-006`) and `docs/handoff.md` are updated
  alongside the change that closes them (T-013, T-014) — only once real, passing tests exist to
  cite.

## Task List

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-001 | Add `domain/reference.py`: `DataQuality`, `TradingStatus` enums; `PointInTimeValue[T]`; `SecurityReference`; `MarketCalendar` (with `is_settlement_day`). | REQ-001, REQ-002, REQ-003 | done | Generic-model pattern per `plan.md`; keep `frozen=True, extra="forbid"` consistent with every existing domain contract. |
| T-002 | Add `domain/events.py`: `CorporateActionType`, `CorporateActionStatus` enums; `CorporateActionEvent` with `version`/`supersedes_event_id`. | REQ-004 | done | No in-place mutation method exists on the class at all — enforce "never mutated" by omission, not by a runtime check. |
| T-003 | Add `enrichment/__init__.py`, `enrichment/point_in_time.py::resolve_latest_known`. | REQ-005, REQ-006 | done | Pure function; no I/O, no adapter dependency — testable with hand-built `PointInTimeValue` lists alone. |
| T-004 | Add `enrichment/security_master.py::reconcile`, `ReconciliationConflict`. | REQ-007 | done | Compares only the fields named in `plan.md` (currency, country_of_risk, instrument_type) — do not silently expand the reconciled field set beyond what's specified. |
| T-005 | Add `ports/reference_data.py::ReferenceDataPort`, `ports/corporate_actions.py::CorporateActionsPort`. | REQ-008 | done | Follow `ports/solver.py`/`ports/demand.py`'s existing `Protocol` + `@runtime_checkable` convention exactly; no concrete import. |
| T-006 | Add `configs/data_sources/{bloomberg.example.yaml,field_mapping.example.yaml,freshness_policy.yaml}` and `adapters/bloomberg/field_mapping.py::FieldMapping`/loader. | REQ-009 | done | Every mnemonic-shaped string in the example YAML must be a generic illustrative placeholder, not a real proprietary Bloomberg field code copied from documentation. |
| T-007 | Add `adapters/bloomberg/reference.py`, `adapters/bloomberg/corporate_actions.py` (synthetic, fixture-backed port implementations) plus their hand-authored fixture data. | REQ-010 | done | No network call, no vendor SDK import anywhere in this module. |
| T-008 | Add `enrichment` (or `adapters/bloomberg`) health-check function `check_bloomberg_adapter_health` and wire a new `bloomberg-doctor` CLI subcommand in `cli.py`. | REQ-011 | done | Mirror `_cmd_doctor`'s existing exception-to-check-result convention; assert no credential-shaped string ever appears in the report or its JSON serialization. |
| T-009 | Extend `validation/reconciliation.py`: `check_security_tradability` (default-empty `references` mapping), `check_settlement_calendar` (default-empty `calendars` mapping) — both return `tuple[str, ...]` warnings, never raise. Wire `check_security_tradability` into `facade.InventoryOptimizer.optimize()` via a new optional `security_references` parameter, merged into `result.warnings`. | REQ-012, REQ-013 | done | Both must return zero warnings when their mapping argument is empty/omitted — the exact byte-identical-when-absent guarantee (NFR-001). |
| T-010 | Add optional `calendars: Mapping[str, MarketCalendar] | None = None` (keyed by currency) to `settlement.project.project_multi_period` and `formulation.multi_period.solve_multi_period`; call `check_settlement_calendar` only when supplied and merge into each module's existing `warnings` accumulation. | REQ-014 | done | Run `specs/0010-multi-period-settlement/`'s existing tests unchanged *before* writing this task's new tests, per `plan.md`'s Validation Strategy step 2 — this is the regression gate for RISK-002. |
| T-011 | Extend `tests/unit/test_architecture_boundaries.py`: scan for known Bloomberg mnemonic patterns outside `adapters/bloomberg/`. | REQ-008, NFR-002 | done | Mirrors the file's existing `highspy`/`pandas` isolation checks; add Bloomberg as a third isolated concern. |
| T-012 | Tests: `tests/unit/test_domain_reference.py`, `test_domain_events.py`, `test_point_in_time.py` (including the hypothesis-based no-look-ahead property test), `test_security_master.py`, `test_field_mapping.py`, `test_bloomberg_adapter.py`, `test_bloomberg_doctor.py`, `tests/unit/test_reconciliation_bloomberg.py`, and additions to the existing multi-period/settlement test files. Confirm the full pre-existing suite (277 passed) still passes unchanged. | REQ-001 through REQ-015, NFR-001 through NFR-005 | done | See Test Coverage Map below for the AC-to-test mapping. 49 new tests; 326 passed total, zero regressions. |
| T-013 | Update `specs/engine_spec/TRACEABILITY.md`: `DAT-001` through `DAT-006` gain evidence pointers; note explicitly which parts stay `SPECIFIED` (real vendor SDK, override-record reconciliation path, R1 economics). | REQ-001 through REQ-015 | done | Only after T-012's tests actually pass — evidence pointers must cite real, passing tests, per `0009`'s own T-009 precedent. |
| T-014 | Update `docs/handoff.md` and `specs/README.md`: record this spec as Implemented, restate that R1 (T22-T24) remains unscoped, and note the real-adapter follow-up explicitly. | REQ-001 through REQ-015 | done | Last task, after T-011/T-012/T-013. A separate, earlier handoff/README edit already exists recording this spec as *Proposed* (required by the `handoff-sync` gate at spec-creation time) — this task upgrades that entry, it does not create a new one. |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | `test_point_in_time.py::test_future_observed_value_is_invisible_before_known_as_of` (plus the `hypothesis` property test, `::test_property_resolution_never_sees_a_value_observed_after_known_as_of`) | done |
| AC-002 | `test_domain_events.py::test_amendment_preserves_prior_version` | done |
| AC-003 | `test_security_master.py::test_conflicting_currency_raises_reconciliation_conflict` | done |
| AC-004 | `test_reconciliation_bloomberg.py::test_optimize_without_security_references_is_byte_identical`; `test_settlement_project.py::test_no_calendar_matches_0010_baseline`; `test_multi_period_lp_compiler.py::test_solve_multi_period_no_calendar_matches_pre_0011_baseline`; `test_reconciliation_bloomberg.py::test_apply_scenario_without_calendars_is_unaffected` | done |
| AC-005 | `test_reconciliation_bloomberg.py::test_halted_security_with_new_route_produces_a_warning`, `::test_optimize_surfaces_warning_for_halted_security` | done |
| AC-006 | `test_reconciliation_bloomberg.py::test_apply_scenario_warns_on_holiday_settlement_date` | done |
| AC-007 | `test_settlement_project.py::test_calendar_rejects_invalid_period_date`, `::test_no_calendar_matches_0010_baseline`; `test_multi_period_lp_compiler.py::test_solve_multi_period_calendar_warns_on_invalid_period_date`, `::test_solve_multi_period_no_calendar_matches_pre_0011_baseline` | done |
| AC-008 | `test_bloomberg_doctor.py::test_health_report_contains_no_credential_shaped_string`, `::test_bloomberg_doctor_cli_command_succeeds` | done |
| AC-009 | `test_field_mapping.py::test_version_bump_does_not_rewrite_prior_values` | done |
| AC-010 | full suite (`pytest tests/ -q`): 326 passed (up from 277 pre-this-spec), zero regressions; `pytest tests/ -m slow -q`: 4 passed unchanged | done |
| AC-011 | `test_architecture_boundaries.py::test_no_bloomberg_mnemonic_outside_adapter` | done |

## Follow-ups

Tracked work intentionally deferred (no silent "temporary" shortcuts — P8).

- **A real Bloomberg-SDK-backed adapter** implementing `ReferenceDataPort`/`CorporateActionsPort`
  against actual entitlements — blocked on the firm's confirmed data catalog per §22.1; this spec's
  synthetic adapter is the complete deliverable until that exists.
- **A configured-override reconciliation path** (§22.1's other sanctioned option, alongside the
  exception path this spec ships) — no desk need identified yet.
- **R1 (T22-T24):** legal-entity hierarchy aggregation, take-up/survival/repricing expected
  economics, dynamic liquidity buffers and PWL unwind costs. Depends on T19/T20 (this spec) per
  `01_SPEC.md` §26's task matrix; not started.
- **Full corporate-action economics** (§22.8's quantity-transformation/cash-flow/election handling)
  — this spec only models timing/identity/status, not the LP-level economic consequences.
- **`ports/market_data.py`, `ports/entity_data.py`, `ports/liquidity_data.py`** and their
  corresponding `adapters/bloomberg/{pricing,entities,liquidity,funds,events}.py` — R1+, not created
  by this spec (see `plan.md`'s Module layout note).
- **Additional `DataQuality` values** (e.g. `UNENTITLED`, `FUTURE_EFFECTIVE`) once a real adapter
  can actually produce them.
