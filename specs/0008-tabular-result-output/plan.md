# Plan: Tabular result output (reporting tables + adapters layer)

- **Spec:** 0008-tabular-result-output (`spec.md`)
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code)
- **Last updated:** 2026-09-05

> HOW. This plan requires an approved `spec.md`. Every requirement in the spec
> must appear in the traceability matrix below.

## Approach

Split the work along `01_SPEC.md` §7.1's own ownership line, so the optional dependency lands at
the boundary and nowhere else:

- **`reporting/tables.py` owns the content** — which tables exist, which columns each has, and how
  a result object's fields map into rows. Pure Python: imports only `domain` plus the standard
  library. No pandas, no formulation/solver types, no I/O. This is what makes the table set
  testable in the current `.venv` (which has no pandas) and keeps §7.1's "reporting owns tables"
  row real.
- **`adapters/` owns the transport** — `csv_io.py` (standard library only) and `dataframe.py`
  (the single module in the package permitted to import pandas, lazily). Neither module knows
  anything about *which* tables exist; they take a `Table` and emit a format.
- **`cli.py` owns the user surface** — one new `tables` subcommand, following the existing
  `_cmd_*`/dispatch/exit-code conventions exactly.

Nothing recomputes anything: every cell is a field read off an already-assembled result object
(REQ-010). That is the difference between this spec and an "analytics" layer — it changes the
*shape* of existing output, never its content.

## The `Table` type (REQ-001)

```python
Cell: TypeAlias = str | float | int | bool | None

@dataclass(frozen=True, slots=True)
class Table:
    name: str                              # file/frame name, e.g. "allocations"
    columns: tuple[str, ...]
    rows: tuple[tuple[Cell, ...], ...]
```

Frozen and slotted, matching every other internal record in this package (`VariableKey`,
`ScalingMetadata`, `VerificationReport`). Deliberately *not* a Pydantic model: it is an internal
projection, not a boundary contract that needs validation or JSON schema — the boundary contract is
`OptimizationResult`, which is already Pydantic and already validated upstream.

Cell normalization rules, applied once in `tables.py` so both adapters inherit them:

| Source shape | Cell |
| --- | --- |
| `StrEnum` (`SolverStatus`, `ReasonCode`, `ProblemFamily`) | its `.value` string |
| `AwareDatetime` | `.isoformat()` string |
| `tuple[StrEnum, ...]` (e.g. `reason_codes`) | `"\|"`-joined `.value` strings, `""` when empty |
| `tuple[str, ...]` (e.g. `warnings`) | `"\|"`-joined, `""` when empty |
| `None` (optional fields, absent `desk`) | `None` (empty CSV cell) |
| `Mapping` | never inlined — emitted as its own long-format table (RISK-002) |

## Table catalogue (REQ-002, REQ-003, NFR-003)

Names and column order below are the contract NFR-003 pins. `result_tables` returns 1-7 in this
order; `scenario_tables` returns 8-11; `stress_tables` returns 12-13.

**From `OptimizationResult`:**

| # | Table | Grain | Columns |
| --- | --- | --- | --- |
| 1 | `allocations` | one `AllocationRecord` | `route_id`, `inventory_id`, `demand_group_id`, `current_quantity_shares`, `post_quantity_shares`, `increase_shares`, `decrease_shares`, `fee_rate`, `demand_cap_shares`, `eligible`, `reason_codes` |
| 2 | `allocation_evidence` | one evidence entry | `route_id`, `key`, `value` |
| 3 | `balances` | one `BalanceRecord` | `inventory_id`, `pre_total_lendable_shares`, `pre_reserved_shares`, `pre_committed_out_shares`, `pre_on_loan_shares`, `pre_available_to_lend_shares`, `post_available_shares`, `post_on_loan_shares`, `utilization` |
| 4 | `demand` | one `DemandSummary` | `demand_group_id`, `reference_quantity_shares`, `raw_demand_shares`, `effective_cap_shares`, `filled_shares`, `unfilled_shares`, `fill_ratio`, `reason_code` |
| 5 | `constraints` | one `ConstraintActivity` | `row_kind`, `row_scope_id`, `lower`, `upper`, `activity`, `slack`, `dual_value` |
| 6 | `economics` | one `ObjectiveAttributionRecord` | `component_name`, `component_version`, `unscaled_value_usd`, `baseline_value_usd`, `delta_usd` |
| 7 | `run_summary` (wide, default) | exactly one row | `request_id`, `run_id`, `created_at`, `config_hash`, `input_hash`, `package_version`, `backend_version`, `status`, `native_status`, `strict`, `termination_reason`, `objective_total_value_usd`, `objective_total_delta_usd`, `solver_backend_name`, `solver_backend_version`, `solver_runtime_seconds`, `solver_iterations`, `solver_nodes`, `solver_best_bound`, `solver_relative_gap`, `solver_termination_reason`, `verification_has_primal`, `verification_max_variable_bound_violation`, `verification_max_row_violation`, `verification_max_integrality_violation`, `verification_objective_reconstruction_delta`, `verification_passed`, `desk_problem_family`, `desk_legal_entity_id`, `desk_platform_tenant_id`, `desk_attribution_scope`, `warnings` |
| 7L | `run_summary_long` (opt-in) | one row per wide column | `run_id`, `key`, `value` |

**From `ScenarioComparison`** (each table carries `scenario_id` so a multi-scenario run's tables
concatenate cleanly):

| # | Table | Grain | Columns |
| --- | --- | --- | --- |
| 8 | `scenario_summary` | one comparison | `scenario_id`, `scenario_name`, `baseline_run_id`, `scenario_run_id`, `status`, `verification_passed`, `objective_delta_usd`, `unfilled_demand_delta_shares`, `config_hash`, `baseline_input_hash`, `scenario_input_hash`, `warnings` |
| 9 | `scenario_allocations` | one `RouteAllocationDelta` | `scenario_id`, `route_id`, `baseline_quantity_shares`, `scenario_quantity_shares`, `delta_shares`, `reason_codes`, `estimated_revenue_delta_usd` |
| 10 | `scenario_balances` | one `InventoryBalanceDelta` | `scenario_id`, `inventory_id`, `baseline_total_lendable_shares`, `scenario_total_lendable_shares`, `baseline_available_shares`, `scenario_available_shares`, `baseline_utilization`, `scenario_utilization` |
| 11 | `scenario_economics` | one component delta | `scenario_id`, `component_name`, `delta_usd` |

**From `StressTestReport`:**

| # | Table | Grain | Columns |
| --- | --- | --- | --- |
| 12 | `stress_summary` | exactly one row | `scenario_count`, `feasible_count`, `infeasible_count`, `verification_failed_count`, `worst_case_scenario_id`, `worst_case_objective_delta_usd` |
| 13 | `stress_outcomes` | one `StressScenarioOutcome` | `scenario_id`, `scenario_name`, `status`, `verification_passed`, `objective_delta_usd` |

## Run summary layout (REQ-012)

The run summary is the one table with two genuinely different consumers: a single run pasted into a
spreadsheet wants the wide row (one header, one line, readable left to right), while comparing many
runs wants long pairs (append every run's rows into one frame, then pivot or filter by `key`).
Neither shape serves both, so the caller picks:

```python
class RunSummaryLayout(StrEnum):
    WIDE = "wide"
    LONG = "long"

def result_tables(
    result: OptimizationResult,
    *,
    run_summary_layout: RunSummaryLayout = RunSummaryLayout.WIDE,
) -> tuple[Table, ...]
```

A module-local `StrEnum` rather than a `domain.enums` addition: this is a presentation option, not
a business concept, and `components/registry.py::ComponentKind` already sets the precedent for
infrastructure enums living beside the code that uses them (§7.1: `domain` owns "business records,
IDs, enums", which this is not).

**The long table is derived from the wide one, never hand-maintained separately:**

```python
def run_summary_long_table(result: OptimizationResult) -> Table:
    wide = run_summary_table(result)
    (row,) = wide.rows
    return Table(
        name="run_summary_long",
        columns=("run_id", "key", "value"),
        rows=tuple((result.run_id, column, cell) for column, cell in zip(wide.columns, row)),
    )
```

Consequences, each deliberate:

- **No drift.** Adding a field to the wide table adds it to the long one automatically; there is
  exactly one field list in the codebase, so the two shapes cannot disagree (REQ-012).
- **Key order equals wide column order**, not alphabetical — related fields stay adjacent
  (identity, then status, then economics, then solver, then verification, then desk), and the two
  layouts read the same way top-to-bottom vs. left-to-right. Deterministic either way (REQ-009).
- **`run_id` is both a column and a key row.** That repetition is ordinary tidy-data practice and
  is what makes concatenating many runs' long tables unambiguous — without it, appending two runs
  yields duplicate `key`s with no way to tell them apart.
- **The long layout loses per-column dtype**: every value shares one `value` column, so a
  DataFrame gets `object` dtype and a CSV consumer casts on read. That is the cost of the shape,
  and the reason wide stays the default.
- **Distinct table names** (`run_summary` vs. `run_summary_long`) rather than one name with two
  schemas — a file's name should determine its schema, so a downstream script reading
  `run_summary.csv` can never silently receive long-format rows because someone passed a flag
  upstream (AC-012).

`adapters` needs no changes for this: both shapes are ordinary `Table`s, so CSV and DataFrame
conversion are unaffected. The CLI exposes `--run-summary-layout {wide,long}` (default `wide`) on
the `tables` subcommand.

Design notes:

- **Totals live in `run_summary`, not appended to `economics`** (REQ-009's determinism aside, a
  synthetic TOTAL row would mix grains in one table and break any downstream `sum()`).
- **`economics_component_deltas` and `explanation_evidence` are `Mapping`s**, whose iteration order
  is not part of any upstream contract — both are emitted `sorted()` by key so repeated runs are
  byte-identical (REQ-009).
- **`desk` may be `None`** (`DeskSummary | None`); its four columns are then `None`, keeping
  `run_summary`'s width fixed regardless.
- **`schedules`/`collateral`/`sources` are always `None`** on `OptimizationResult` today (no
  upstream domain model exists — see `VER-006`'s own status note), so they get no tables. When
  those subsystems land, new tables are additive.

## Adapters (REQ-005, REQ-006, REQ-007)

```python
# adapters/csv_io.py -- standard library only
def write_table(table: Table, path: Path) -> None
def write_tables(tables: Sequence[Table], directory: Path) -> tuple[Path, ...]   # <name>.csv each

# adapters/dataframe.py -- sole owner of the pandas import
def to_dataframe(table: Table) -> "pandas.DataFrame"
def to_dataframes(tables: Sequence[Table]) -> dict[str, "pandas.DataFrame"]
```

`csv_io` opens with `newline=""` and writes via `csv.writer(..., lineterminator="\n")` so output is
byte-identical across platforms (AC-005). `None` becomes an empty cell, `bool` becomes
`True`/`False` — `csv`'s own defaults, documented rather than customized.

`dataframe.py` imports pandas *inside* its functions and converts the failure, mirroring
`facade._resolve_backend`'s existing treatment of the optional `highs` extra:

```python
try:
    import pandas
except ImportError as exc:
    raise ConfigurationError(
        "DataFrame output requires the 'dataframe' extra (pip install -e '.[dataframe]')"
    ) from exc
```

This is the whole reason the layer split exists: an eager module-level `import pandas` anywhere in
`reporting/` would make the optional extra mandatory for every caller who merely wants CSVs, and
would break `ARC-003`'s "independently installable" guarantee the same way an eager `highspy`
import would.

## CLI (REQ-008)

```text
inventory-optimizer tables --input result.json --output-dir ./tables \
    [--kind result|scenarios|stress] [--run-summary-layout wide|long]
```

`--run-summary-layout` (default `wide`, REQ-012) applies only to `--kind result`. Passing it
explicitly alongside another `--kind` exits `EXIT_INVALID_INPUT` with a diagnostic naming the
conflict, rather than accepting and ignoring it — silently dropping a flag the caller deliberately
typed is the same failure mode `compile_lp`'s `MIP_REQUIRED`/`QP_REQUIRED` rejections exist to
prevent (constitution P4). Not passing it at all is fine for every `--kind`, since the default then
applies to whichever table set is built.

`--kind` defaults to `result` and is explicit rather than sniffed — the `scenarios` command already
emits *either* a single `ScenarioComparison` object *or* a JSON array of them depending on its
input, so `--kind scenarios` accepts both (mirroring `_load_scenarios`'s existing object-or-array
handling) and concatenates each comparison's rows into one table set. Guessing the type from the
payload's shape would be silent magic in a repo whose constitution is "fail closed, name the
problem."

Exit codes reuse the established scheme: `EXIT_SUCCESS` on write, `EXIT_INVALID_INPUT` for an
unreadable/unparseable/wrong-shape input file (with a stderr diagnostic, never a traceback),
`EXIT_INTERNAL_ERROR` for an unwritable output directory. The command prints the written file paths
as JSON to stdout so it stays machine-composable like every other subcommand.

Deliberately *not* done: adding `--format csv` to `optimize`. That would change `--output`'s
meaning from "a file" to "a directory" depending on a sibling flag, and would drag table-building
into the solve path. Composing `optimize --output result.json && tables --input result.json` keeps
both commands' contracts intact (NFR-002) and works on results saved from earlier runs.

## Import-boundary test (REQ-011)

A self-contained `ast` walk in `tests/unit/test_architecture_boundaries.py`: parse every
`src/inventory_optimizer/adapters/*.py`, collect `Import`/`ImportFrom` module names, and assert
none begins with a disallowed layer prefix, plus that `pandas` appears only in `dataframe.py`.

Deliberately *not* reusing `scripts/verify_portability.py::find_forbidden_imports`: its forbidden
set is a module-level constant tied to `ARC-003`'s specific "no `qr_haven` import" question, which
is already `IMPLEMENTED` and tested. Parameterizing it would widen an already-closed surface to
serve a different requirement; a ~30-line local walk is cheaper and keeps the two concerns
independent.

## Constitution Check

- Spec is source of truth: `spec.md` written first; this plan implements it.
- Traceable: every REQ/NFR below maps to file(s) and test(s).
- Definition of Done: each AC has a named test.
- Correct by construction: tables project fields only (REQ-010), so no output can disagree with the
  `OptimizationResult` it came from; the optional dependency fails with a named, actionable error
  rather than a bare import error.
- No silent trade-offs: the declined `json_io.py`, the declined `optimize --format csv`, the
  declined `verify_portability` reuse, and the long-format evidence table are each recorded with
  reasoning here and in `spec.md`.

## Traceability Matrix

| ID | Evidence | Task |
| --- | --- | --- |
| REQ-001 | `reporting/tables.py::Table`, `Cell` | T-001 |
| REQ-002 | `reporting/tables.py` builders 1-7 | T-002 |
| REQ-003 | `reporting/tables.py` builders 8-13 | T-003 |
| REQ-004 | `reporting/tables.py::result_tables`, `scenario_tables`, `stress_tables` | T-002, T-003 |
| REQ-005 | `adapters/csv_io.py::write_table`, `write_tables` | T-004 |
| REQ-006 | `adapters/dataframe.py::to_dataframe`, `to_dataframes` | T-005 |
| REQ-007 | `adapters/dataframe.py` (sole pandas importer) | T-005, T-007 |
| REQ-008 | `cli.py::_cmd_tables` + parser/dispatch entries; `domain/results.py`'s round-trip fix (`UnboundedBelow`/`UnboundedAbove`, T-012) | T-006, T-012 |
| REQ-009 | `reporting/tables.py`'s sorted-mapping/fixed-column rules; `adapters/csv_io.py`'s line terminator | T-002, T-004, T-008 |
| REQ-010 | `reporting/tables.py` (projection only) | T-002, T-003, T-008 |
| REQ-011 | `tests/unit/test_architecture_boundaries.py` | T-007 |
| REQ-012 | `reporting/tables.py::RunSummaryLayout`, `run_summary_table`, `run_summary_long_table`, `result_tables(..., run_summary_layout=)`; `cli.py`'s `--run-summary-layout` | T-002, T-006 |
| NFR-001 | `adapters/dataframe.py`'s lazy import; `pytest.importorskip` in its tests | T-005, T-008 |
| NFR-002 | Full existing 193-test suite, rerun unchanged | T-008 |
| NFR-003 | The catalogue above; `tests/unit/reporting/test_tables.py`'s column assertions | T-008, T-009 |
| NFR-004 | `tests/unit/test_architecture_boundaries.py` | T-007 |

## Trade-offs & Alternatives

- **Long-format vs. wide evidence table** — wide would need a column per evidence key, and the key
  set varies with which reason codes fired, producing a schema that changes run to run (RISK-002).
  Long format costs one join for the rare consumer who wants it wide, and keeps every other table's
  contract stable.
- **`Table` as a plain frozen dataclass vs. a Pydantic model** — Pydantic would add validation and
  JSON schema this projection does not need; the validated boundary contract is
  `OptimizationResult`, upstream. Cheaper and more honest as a dataclass.
- **CSV via stdlib vs. via pandas** — routing CSV through pandas would make the CLI's most useful
  path depend on the optional extra. Stdlib `csv` costs a few lines and makes the feature work in
  the current `.venv` exactly as it stands (no pandas installed).
- **A `tables` subcommand vs. `optimize --format csv`** — see CLI section above.
- **Run summary: both layouts vs. picking one** — picking one would have forced either the
  spreadsheet consumer or the cross-run comparison consumer to reshape by hand every time. Emitting
  *both* unconditionally was the other alternative, rejected because it writes the same data twice
  on every run and puts a redundant table in a contract NFR-003 has to keep stable. A caller-chosen
  layout, with long derived from wide, costs about ten lines and no duplication.

## Validation Strategy

- `tests/unit/reporting/test_tables.py` — table names/order, exact column tuples per table, one row
  per source record with values equal to the source fields, enum/datetime/tuple normalization,
  sorted mapping order, `desk=None` widths (AC-001, AC-002, AC-003, NFR-003), plus both run-summary
  layouts and the wide-to-long correspondence that proves they cannot drift (AC-011).
- `tests/unit/adapters/test_csv_io.py` — header equals columns, row count, `None`/`bool` rendering,
  and byte-identical repeat writes (AC-004, AC-005).
- `tests/unit/adapters/test_dataframe.py` — `importorskip("pandas")` for the happy path (AC-006);
  a monkeypatched-absent-pandas case asserting `ConfigurationError` names the extra (AC-007), which
  is the behavior every consumer without the extra actually hits.
- `tests/unit/test_cli.py` — extended for the `tables` subcommand's success and invalid-input paths
  (AC-008), the `--run-summary-layout long` file name/schema (AC-012), and the
  layout-flag-with-wrong-`--kind` rejection, reusing the file's existing tmp-path conventions.
- `tests/unit/test_architecture_boundaries.py` — the import walk (AC-009).
- Full suite rerun (AC-010/NFR-002).

Fixtures reuse the existing solved results rather than inventing new ones: `tests/unit/reporting/
conftest.py` already builds a verified solution for the T11 reporting tests, and the scenario/stress
objects come from the same factories `tests/unit/test_scenarios_runner.py` uses.

## Rollout, Observability & Rollback

Almost purely additive: one new module in `reporting/`, one new `adapters/` package, one new CLI
subcommand, plus one small, backward-compatible fix to `domain/results.py` (T-012, discovered
during implementation — see below). No existing module's *behavior* changes and no emitted byte
changes anywhere, so rollback is deleting the new files, the `cli.py` parser/dispatch entries, and
reverting the two `BeforeValidator` type aliases. Observability is the CLI's written-file listing
plus the test suite. `specs/engine_spec/TRACEABILITY.md`'s `ARC-004` row gains partial evidence (the
adapters-layer boundary test) and stays `SPECIFIED` pending the full layer matrix.

**Deviation from approved scope, recorded per the constitution's "no silent trade-offs":**
implementing REQ-008 (the `tables` CLI reading a saved result JSON) surfaced that
`OptimizationResult` could not round-trip its own JSON at all — `ConstraintActivity.lower` (E1's
`demand_cap` rows are one-sided, `-inf`) serializes to `null`, which a plain `float` field then
rejects on read-back. This was a pre-existing, latent defect in T11's `domain/results.py`, invisible
until this spec's command became the first thing to ever read a result back. Fixed with two
`Annotated[float, BeforeValidator(...)]` type aliases mapping `null` back to `-inf`/`+inf` on
`ConstraintActivity` and `VerificationSection`'s violation fields — emitted JSON is byte-identical;
only reading is repaired. `tests/unit/reporting/test_result_builder.py::
test_result_round_trips_through_its_own_json` pins it.

## Open Questions

- Whether the full `ARC-004` layer-matrix import test becomes this spec's follow-up or its own
  spec — deferred either way.

(The former open question — `run_summary` wide vs. long — is resolved: both, caller-selected, per
REQ-012 and the "Run summary layout" section above.)
