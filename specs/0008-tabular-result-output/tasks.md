# Tasks: Tabular result output (reporting tables + adapters layer)

- **Spec:** 0008-tabular-result-output (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-05

> Ordered, testable units of work. Every task cites the requirement(s) it advances
> and carries a Definition of Done. No task without a requirement.

**Status note:** approved; implementation in progress. Every task below starts `todo`; none of this spec is
built yet.

## Definition of Done (applies to every task)

- Code matches `plan.md`; deviations noted there before merge, not silently.
- Tests exist and pass deterministically (`pytest tests/ -q`).
- Reproducibility preserved (no wall-clock/random state; mapping iteration explicitly sorted).
- No secrets, credentials, or private data introduced.
- Every existing test continues to pass unchanged (NFR-002) — nothing here may alter
  `optimize`/`scenarios` output, exit codes, or the `OptimizationResult` contract.
- `pandas` stays optional: the default test run and the whole CSV path work with the extra absent
  (NFR-001), which is the current `.venv`'s actual state.
- `specs/spec002/TRACEABILITY.md`'s `ARC-004` row and `docs/handoff.md` are updated alongside the
  change that touches them (T-010, T-011).

## Task List

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-001 | Add `reporting/tables.py`'s `Cell` alias and frozen `Table` dataclass plus the shared cell-normalization helpers (enum `.value`, datetime `.isoformat()`, tuple joining, `None` passthrough). | REQ-001 | todo | Pure: `domain` + stdlib only, no pandas, no I/O (NFR-004). |
| T-002 | Add the seven `OptimizationResult` table builders and `result_tables()`, including `RunSummaryLayout` and the wide/long run-summary pair. | REQ-002, REQ-004, REQ-009, REQ-010, REQ-012 | todo | Column names/order per `plan.md`'s catalogue; `explanation_evidence` emitted long-format and key-sorted; `run_summary_long_table` derived from the wide table so one field list serves both shapes. |
| T-003 | Add the four `ScenarioComparison` and two `StressTestReport` builders plus `scenario_tables()`/`stress_tables()`. | REQ-003, REQ-004 | todo | Every scenario table carries `scenario_id` so multi-scenario runs concatenate. |
| T-004 | Add `adapters/__init__.py` and `adapters/csv_io.py` (`write_table`, `write_tables`). | REQ-005, REQ-009 | todo | Standard library only; `newline=""` + `lineterminator="\n"` for byte-stable output. |
| T-005 | Add `adapters/dataframe.py` (`to_dataframe`, `to_dataframes`) with the lazy pandas import and `ConfigurationError` naming the extra. | REQ-006, REQ-007, NFR-001 | todo | Mirrors `facade._resolve_backend`'s existing optional-extra handling for `highs`. |
| T-006 | Add the `tables` CLI subcommand (`_cmd_tables`, parser entry, dispatch entry) with `--input`, `--output-dir`, `--kind`, `--run-summary-layout`. | REQ-008, REQ-012 | todo | No change to any existing subcommand; `--kind scenarios` accepts object-or-array like `_load_scenarios` already does; an explicit layout flag with a non-`result` kind is rejected, not silently ignored (constitution P4). |
| T-007 | Add `tests/unit/test_architecture_boundaries.py`: `adapters/*` imports no disallowed layer, and `pandas` appears only in `adapters/dataframe.py`. | REQ-007, REQ-011, NFR-004 | todo | Self-contained `ast` walk; deliberately not reusing `scripts/verify_portability.py` (see `plan.md`). |
| T-008 | Tests: `tests/unit/reporting/test_tables.py`, `tests/unit/adapters/test_csv_io.py`, `tests/unit/adapters/test_dataframe.py`, and `tests/unit/test_cli.py` additions. Confirm all pre-existing tests still pass (AC-010). | REQ-001 through REQ-010, NFR-001 through NFR-003 | todo | See Test Coverage Map below. |
| T-009 | Document the emitted table/column contract for consumers (README or `docs/`), pointing at `plan.md`'s catalogue as the normative list. | NFR-003 | todo | Small: the contract exists to be depended on, so it needs a discoverable home outside the spec directory. |
| T-010 | Update `specs/spec002/TRACEABILITY.md`'s `ARC-004` row: add the adapters-layer boundary test as evidence; status stays `SPECIFIED` with a note that full closure needs boundary tests for every layer pair. | REQ-011 | todo | Mirrors the partial-evidence honesty pattern already used for `LP-008`/`PLT-002`/`VER-005`. |
| T-011 | Update `docs/handoff.md` and `specs/README.md`: record this spec, the new `adapters/` layer, and the fact that the `dataframe` extra now has a real consumer. | REQ-005, REQ-006 | todo | Also correct the Environment block, which currently implies `pandas` is installed in the `.venv` when it is not. |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | `test_tables.py::test_result_tables_names_and_order`, `::test_allocations_columns_match_contract`, `::test_allocations_row_per_record` | todo |
| AC-002 | `test_tables.py::test_reason_codes_joined_on_allocations`, `::test_evidence_emitted_long_format_sorted` | todo |
| AC-003 | `test_tables.py::test_scenario_tables_row_per_delta`, `::test_stress_tables_row_per_outcome` | todo |
| AC-004 | `test_csv_io.py::test_header_and_rows_written` | todo |
| AC-005 | `test_csv_io.py::test_repeat_write_is_byte_identical` | todo |
| AC-006 | `test_dataframe.py::test_to_dataframe_columns_and_shape` (`importorskip`) | todo |
| AC-007 | `test_dataframe.py::test_missing_extra_raises_configuration_error` | todo |
| AC-008 | `test_cli.py::test_tables_writes_csvs`, `::test_tables_rejects_unreadable_input` | todo |
| AC-009 | `test_architecture_boundaries.py::test_adapters_layer_imports_stay_within_boundary`, `::test_pandas_imported_only_by_dataframe_adapter` | todo |
| AC-010 | Existing suite (193 tests, pre-this-spec) still passing unchanged | todo |
| AC-011 | `test_tables.py::test_run_summary_wide_is_single_row`, `::test_run_summary_long_matches_wide_keys_and_values` | todo |
| AC-012 | `test_cli.py::test_tables_long_layout_writes_distinct_file`, `::test_tables_rejects_layout_flag_for_non_result_kind` | todo |

## Follow-ups

Tracked work intentionally deferred (no silent "temporary" shortcuts — P8).

- Full `ARC-004` closure — an import-graph test across every layer pair in §7.1's ownership table,
  not just `adapters`. Possibly its own small spec, in `specs/0005-test-hardening/`'s style.
- Charts, dashboards, Excel workbooks, and narrative summaries stay out of scope; the QuantSmith
  dashboard surfaces were already evaluated and parked (`docs/handoff.md`).
- `schedules`/`collateral`/`sources` get no tables until their upstream domain models exist
  (`VER-006`'s own status note); adding them later is additive.
- Extending the wide/long layout choice to other tables (e.g. `stress_summary`) is additive and
  deliberately deferred — see `spec.md`'s Non-Goals for why only the run summary gets it now.
- Streaming/chunked writing for results beyond the in-memory ceiling `OptimizationResult` assembly
  already assumes.
