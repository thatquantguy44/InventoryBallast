# Spec: Tabular result output (reporting tables + adapters layer)

- **ID:** 0008-tabular-result-output
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code)
- **Approver:** Joshua Lutkemuller, CFA (2026-09-05 — "0008 first", sequencing this ahead of `specs/0009-discrete-fee-tier-pricing/`; the spec's remaining questions were accepted at their proposed defaults, including the saved-JSON `tables` input shape, the long-format evidence table, and deferring the full `ARC-004` layer-matrix import test)
- **Last updated:** 2026-09-05

> WHAT and WHY only. No implementation detail — that belongs in `plan.md`.

## Problem & Context

`specs/engine_spec/01_SPEC.md` §7 names two surfaces this repo has never built:

- **`reporting/tables.py`** — the §7 package tree lists it alongside the already-built
  `attribution.py`/`serialization.py` siblings, and §7.1 makes `reporting` own "Tables,
  attribution, serialization." T11 built attribution and (via Pydantic) serialization. Tables were
  skipped.
- **`adapters/`** — §7.1 gives the layer its own ownership row ("JSON and optional dataframe
  conversion"), and the §7 package tree names `adapters/json_io.py` and `adapters/dataframe.py`
  (annotated in the spec's own tree as "optional tabular boundary adapter"). The package does not
  exist at all; `ports/__init__.py`'s docstring already promises callers that "concrete adapters
  live in `solvers/`, `adapters/`, and platform-owned integration code."

`pyproject.toml` has declared a `dataframe` extra (`pandas>=2.2`) since Phase 0A with **zero usage
anywhere in `src/`** (verified by grep: no `import pandas`, no `DataFrame` reference) — the same
dormant-scaffold pattern `Formulation.QP`, `Capability.CONTINUOUS_QP`, and `ScalingMetadata` all
showed before Phases 3-4 populated them. It is also **not installed in the working `.venv`**,
despite `docs/handoff.md`'s Environment block showing it in the install command — so nothing has
ever exercised it, and this spec must treat the dependency as genuinely optional rather than
assume it is present.

Today the only machine-consumable output is `OptimizationResult` JSON (`cli.py`'s `optimize
--output`, or `model_dump_json()` from the facade). That contract is complete and faithful, and
this spec does not change it. But it is *nested*: `allocations`, `balances`, `demand`,
`constraints`, and `economics.components` are all arrays of objects, and `AllocationRecord` carries
a further nested `reason_codes` tuple plus a free-form `explanation_evidence` mapping. Answering an
ordinary desk question — "which routes moved most?", "which rows bound?", "what did each objective
component contribute?" — means writing a JSON-flattening script first, every time, per consumer.
That flattening is a boundary concern the architecture already assigns a home; it is simply
unbuilt.

`TRACEABILITY.md`'s `ARC-004` ("Domain, schedules, formulation, solver, scenarios, services,
reporting, and adapters remain separated", `SPECIFIED`) is a related, partially-blocked row: a
layer named in §7.1 that does not exist cannot be demonstrated separated. This spec builds the
layer and adds its boundary test; full `ARC-004` closure needs boundary tests for every layer pair
and stays out of scope (see Non-Goals).

## Goals

- A pure, dependency-free `reporting.tables` module defining a small immutable `Table`
  (name, ordered columns, ordered rows of scalars) plus one builder per repeated section of the
  three public result types — `OptimizationResult`, `ScenarioComparison`, and `StressTestReport` —
  projecting fields that already exist, never recomputing anything.
- A caller-selectable layout for the run summary — one wide row (spreadsheet-friendly header) or
  long `key`/`value` pairs (append-friendly across many runs) — since the two shapes serve
  genuinely different consumers and neither is right for both.
- A new `adapters/` package: `csv_io.py` writing tables with the standard library only (so the
  feature works with no optional extras installed at all), and `dataframe.py` as the sole owner of
  the `pandas` import — lazily imported, raising a clear, actionable error naming the extra when it
  is absent, exactly as `facade._resolve_backend` already does for the `highs` extra.
- An `inventory-optimizer tables` CLI subcommand that reads a previously-emitted result or
  comparison JSON and writes one CSV per table into a directory — composable with the existing
  `optimize`/`scenarios` commands rather than changing either of their current output contracts.
- An import-boundary test proving the new `adapters` layer depends only on `domain`/`reporting`
  (plus the standard library and its own optional `pandas`), adding real evidence to `ARC-004`.
- Documentation of the emitted column contract, so downstream CSV/DataFrame consumers know what is
  stable and what a change to it means.

## Non-Goals

- **`adapters/json_io.py` as its own module** — the §7 package tree names it, but Pydantic v2
  *is* this repo's JSON transport already (`model_dump_json`/`model_validate_json`, used by
  `cli.py` today for both directions). A wrapper module would add indirection without capability.
  Declined deliberately, recorded here rather than silently skipped.
- **Charts, dashboards, HTML, or Excel workbooks** — `docs/handoff.md`'s QuantSmith evaluation
  already assessed `DashboardSpec`/`render_streamlit`/`write_xlsx` concretely and parked them
  ("metadata-only ... needs real reshaping, not glue code"). Nothing here revisits that.
- **Narrative/prose summaries** ("the desk should do X because Y") — `reporting/explanations.py`
  already derives structured `ReasonCode`s; rendering those as sentences is a presentation decision
  with its own audience questions, not a tabular-output concern.
- **New analytics, derived metrics, ratios, or rankings** — every column projects a field that
  already exists on a result object. §7.1: `reporting` must not own "re-solving or changing
  results", and inventing derived measures here would put analytical policy in a formatting layer.
- **Aggregation, pivoting, filtering, or group-bys** — the consumer's job once tidy tables exist;
  pandas/Excel already do this better than a bespoke API would.
- **Full `ARC-004` closure** — proving *every* layer pair separated needs an import-graph test
  across all of `domain`/`ports`/`validation`/`elasticity`/`components`/`formulation`/`solvers`/
  `scenarios`/`services`/`reporting`/`adapters`. This spec adds the `adapters`-layer boundary test
  only; the full matrix is a tracked follow-up (and plausibly its own small spec).
- **Wide/long layout options for tables other than the run summary** — REQ-012's choice exists
  because the run summary is ~30 columns wide *and* has a real cross-run comparison use case. The
  other single-row table (`stress_summary`, six columns, already an aggregate across scenarios) and
  every per-record table stay one shape; extending the option later is additive, and doing it
  pre-emptively would multiply the contract surface NFR-003 has to hold stable.
- **Streaming or chunked output for very large results** — tables are built in memory, matching
  how `OptimizationResult` itself is already assembled and serialized.
- **Changing `optimize`/`scenarios` output** — their JSON contracts and exit codes are untouched;
  `tables` is additive and reads what they already emit.

## Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| REQ-001 | The system shall provide `reporting.tables.Table`: an immutable, dependency-free record of a table `name`, an ordered tuple of `columns`, and an ordered tuple of `rows` whose cells are `str \| float \| int \| bool \| None`. | must |
| REQ-002 | The system shall provide `reporting.tables` builders projecting `OptimizationResult` into tables for allocations, allocation evidence, balances, demand, constraints, objective-component economics, and a single-row run summary. | must |
| REQ-003 | The system shall provide `reporting.tables` builders projecting `ScenarioComparison` (summary, allocation deltas, balance deltas, economics-component deltas) and `StressTestReport` (summary, per-scenario outcomes) into tables. | must |
| REQ-004 | The system shall provide `reporting.tables.result_tables(result)`, `scenario_tables(comparison)`, and `stress_tables(report)` returning every table for that object, in a fixed, documented order. | must |
| REQ-005 | The system shall provide `adapters.csv_io` writing a `Table` to CSV using only the standard library, and writing a whole table set into a directory as one `<table name>.csv` file each. | must |
| REQ-006 | The system shall provide `adapters.dataframe.to_dataframe(table)` and `to_dataframes(tables)`, importing `pandas` lazily and raising `ConfigurationError` naming the `dataframe` extra when it is not installed — mirroring `facade._resolve_backend`'s existing handling of the optional `highs` extra. | must |
| REQ-007 | `adapters/dataframe.py` shall be the only module in `src/inventory_optimizer/` that imports `pandas`. | must |
| REQ-008 | The CLI shall gain a `tables` subcommand taking a saved result/comparison/stress JSON plus an output directory, writing one CSV per table and reporting the files written, using the established `_cmd_*`/dispatch/exit-code conventions (invalid input, internal error) without altering any existing subcommand. | must |
| REQ-009 | Table row order shall follow the source object's own tuple order, and column order shall be fixed per table, so repeated runs over the same result produce byte-identical CSV output. | must |
| REQ-010 | Every table column shall project an existing field of the source object; no builder may recompute an objective, re-solve, or derive a new metric. | must |
| REQ-011 | The system shall provide an import-boundary test asserting `adapters/*` imports nothing from `formulation`, `solvers`, `services`, `scenarios`, `components`, `validation`, or `config`. | must |
| REQ-012 | The run summary shall be available in either of two layouts, selected by the caller (Python API keyword and CLI flag), defaulting to wide: `wide` — one row whose columns are the summary fields; `long` — one row per field with `run_id`, `key`, `value` columns, so summaries from many runs concatenate into one frame. The long layout shall be derived from the wide table's own columns and row rather than a separately-maintained field list, and shall preserve the wide column order, so the two shapes cannot drift apart. | must |

## Non-Functional Requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | `pandas` stays genuinely optional | `import inventory_optimizer`, the full default test run, and the entire `tables` CLI path (CSV) all work with `pandas` absent — the state of the current `.venv`. Only `adapters.dataframe`'s own functions require it, and their tests `pytest.importorskip` cleanly rather than failing. |
| NFR-002 | No change to existing outputs | Every existing test continues to pass unchanged (193 pre-this-spec); `optimize`/`scenarios` JSON, exit codes, and the `OptimizationResult` contract are untouched. |
| NFR-003 | The emitted column set is a contract | Table names and column names/order are documented in `plan.md` and treated as a breaking change if altered, because CSV and DataFrame consumers index by them. Both run-summary layouts (REQ-012) are contracts: the wide column list, and the long layout's `run_id`/`key`/`value` shape plus its key ordering. |
| NFR-004 | Layer boundary honored | `reporting.tables` imports only `domain` + the standard library (no pandas, no formulation/solver types), keeping §7.1's ownership split real rather than nominal. |

## Acceptance Criteria

| ID | Given / When / Then | Covers |
| --- | --- | --- |
| AC-001 | Given a solved `OptimizationResult` from an existing golden fixture, when `result_tables(result)` is called, then it returns the documented tables in the documented order, each with its documented columns, and the allocations table has exactly one row per `AllocationRecord` with values equal to that record's own fields. | REQ-001, REQ-002, REQ-004, REQ-010 |
| AC-002 | Given a result whose allocations carry `reason_codes` and `explanation_evidence`, when tables are built, then reason codes appear as a joined string column on the allocations table and each evidence entry appears as its own row in the long-format evidence table keyed by `route_id`. | REQ-002 |
| AC-003 | Given a `ScenarioComparison` and a `StressTestReport` from the existing scenario-engine fixtures, when `scenario_tables`/`stress_tables` are called, then each returns the documented tables with one row per delta/outcome record. | REQ-003, REQ-004 |
| AC-004 | Given any table, when written via `adapters.csv_io` with `pandas` not installed, then a valid CSV is produced with the header row equal to the table's columns and one line per row. | REQ-005, NFR-001 |
| AC-005 | Given the same result written twice to different directories, when the CSV files are compared, then they are byte-identical. | REQ-009 |
| AC-006 | Given `pandas` is installed, when `to_dataframe(table)` is called, then the frame's `columns` equal the table's columns and its row count equals the table's row count. (Skipped via `importorskip` when the extra is absent.) | REQ-006 |
| AC-007 | Given `pandas` is not installed, when `to_dataframe` is called, then it raises `ConfigurationError` whose message names the `dataframe` extra and the install command — never a bare `ModuleNotFoundError`. | REQ-006, NFR-001 |
| AC-008 | Given a saved `OptimizationResult` JSON, when `inventory-optimizer tables --result result.json --output-dir DIR` runs, then it exits `0` and `DIR` contains one CSV per documented table; given a malformed or missing file, then it exits with the invalid-input code and a stderr diagnostic, never a traceback. | REQ-008 |
| AC-009 | Given the whole `src/inventory_optimizer` tree, when the import-boundary test runs, then `adapters/*` is shown to import nothing from the disallowed layers, and `pandas` appears in no module other than `adapters/dataframe.py`. | REQ-007, REQ-011, NFR-004 |
| AC-010 | Given every pre-existing test in the suite (193, pre-this-spec), when run after this spec's changes, then all still pass unchanged. | NFR-002 |
| AC-011 | Given one solved result, when tables are built with the wide layout and again with the long layout, then the wide run summary has exactly one row and the long one has exactly one row per wide column; every long row's `run_id` equals the result's own `run_id`; the long `key` sequence equals the wide column order exactly; and each long `value` equals the wide row's cell for that key. | REQ-012, REQ-009 |
| AC-012 | Given `inventory-optimizer tables` run with `--run-summary-layout long`, then the emitted summary CSV carries the long schema and is named distinctly from the wide one, so a file's name determines its schema. | REQ-012, REQ-008 |

## Data & Dependencies

- `domain.results.OptimizationResult` and its section models (`AllocationRecord`, `BalanceRecord`,
  `DemandSummary`, `ConstraintActivity`, `ObjectiveAttributionRecord`, `EconomicsSummary`,
  `SolverDiagnostics`, `VerificationSection`, `DeskSummary`) — read-only sources for REQ-002.
  Building `tables --input` (REQ-008) surfaced that `ConstraintActivity`/`VerificationSection`
  could not round-trip through their own JSON (an unbounded `-inf`/`+inf` field serializes to
  `null`, which then failed validation on read-back — nothing had read a result back before this
  spec's CLI command did). Fixed alongside this spec (two `BeforeValidator` type aliases,
  `plan.md`); emitted JSON is unchanged, only reading is repaired.
- `domain.scenario_results.ScenarioComparison`, `StressTestReport`, `RouteAllocationDelta`,
  `InventoryBalanceDelta`, `StressScenarioOutcome` — read-only sources for REQ-003.
- `exceptions.ConfigurationError` — reused for REQ-006's missing-extra error (no new exception
  type).
- `pyproject.toml`'s existing `dataframe` extra — first actual consumer.
- `cli.py`'s subparser/dispatch/exit-code conventions (T12) — extended by REQ-008, unchanged
  otherwise.
- `specs/engine_spec/TRACEABILITY.md`'s `ARC-004` row — gains partial evidence (adapters-layer boundary
  test); stays `SPECIFIED` pending the full layer matrix.

## Risks

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| RISK-001 | Column names/order become a de-facto public contract the moment anyone builds a spreadsheet or script on the CSVs, but nothing in the repo enforces that contract's stability. | A later "harmless" rename silently breaks downstream consumers with no test failure here. | NFR-003 makes the contract explicit, `plan.md` documents every column, and AC-001/AC-005 pin names, order, and byte-stability in tests — so a change fails loudly in CI rather than quietly downstream. |
| RISK-002 | `AllocationRecord.explanation_evidence` is a free-form `Mapping[str, float \| str]`, so its keys vary by which reason codes fired; flattening it into columns would produce ragged, unstable schemas. | An evidence-derived column set would change shape run to run, breaking RISK-001's contract immediately. | Emitted as a separate long-format table (`route_id`, `key`, `value`) with `value` stringified — stable schema regardless of which keys appear (AC-002). |
| RISK-003 | `pandas` is optional and currently absent from the working `.venv`, so the DataFrame path is the least-exercised surface in this spec. | A latent breakage in `adapters/dataframe.py` could go unnoticed locally and only surface for a consumer who installed the extra. | The CSV path (stdlib) carries the CLI and needs no extra at all; DataFrame tests use `pytest.importorskip` so they run wherever the extra *is* installed (including CI if it installs it), and AC-007 pins the absent-extra behavior itself, which is the failure mode a user without the extra actually hits. |
| RISK-004 | Very large results (Core-desk scale: tens of thousands of allocation rows) build every table in memory before writing. | Memory pressure or a slow `tables` run at the top end of scale. | Explicitly a Non-Goal to stream; the same in-memory assumption already governs `OptimizationResult` assembly and JSON serialization upstream, so this adds no new ceiling. Revisit only if a real result exceeds it. |

## Assumptions & Open Questions

- Assumption: the tidy long-format evidence table (RISK-002) is more useful than a wide, ragged one
  for the analyst workflows this targets (pivot/filter in pandas or Excel). If real usage shows
  otherwise, widening it is additive and non-breaking to the other tables.
- Assumption: `tables` reading a *saved* JSON (rather than optimizing inline) is the right shape —
  it composes with `optimize`/`scenarios`, works on results from earlier runs, and keeps the
  optional dependency and the solver path completely separate. An inline `optimize --format csv`
  would couple them and would change an existing command's `--output` semantics from file to
  directory.
- Resolved (was an open question): `run_summary` supports **both** shapes, chosen by the caller
  (REQ-012), because the wide row suits a single run pasted into a spreadsheet while the long form
  suits appending many runs into one frame to compare across them — neither serves both, and the
  cost of supporting both is one derived projection rather than a second field list.
- Open question: whether a future `ARC-004` full-matrix import test belongs in this spec's
  follow-ups or its own small spec alongside `specs/0005-test-hardening/`'s style. Deferred.

## Exceptions

None recorded.
