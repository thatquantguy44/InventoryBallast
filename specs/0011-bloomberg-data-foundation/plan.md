# Plan: Bloomberg data foundation (Realism release R0)

- **Spec:** 0011-bloomberg-data-foundation (`spec.md`)
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code)
- **Last updated:** 2026-09-14

> HOW. This plan requires an approved `spec.md`. Every requirement in the spec must appear in the
> traceability matrix below.

**Resolved (2026-09-14):** synthetic-only adapter confirmed sufficient; REQ-012/REQ-013 are
non-blocking warnings, not hard failures (this changes the Validation wiring section below
materially from its original hard-fail sketch); REQ-012's "new route" definition
(`current_quantity_shares == 0`) is adopted as a V0 default despite the owner calling it
uncertain — see `spec.md`'s RISK-003.

## Approach

Follow the boundary this repo already enforces everywhere else — `solvers/highs.py` is the sole
owner of `highspy`, `adapters/dataframe.py` is the sole owner of `pandas` — and apply it to the
vendor that does not exist here yet: **`adapters/bloomberg/` is the sole module tree permitted to
know a Bloomberg field mnemonic.** Everything above it (`domain/`, `ports/`, `enrichment/`,
`validation/`, `formulation/`) speaks only in the business-concept vocabulary §22.3 defines.

Because there is no real vendor SDK to gate behind a lazy import (`solvers/highs.py`'s pattern),
the containment direction is reversed here: instead of "optional dependency, present or absent,"
this spec ships **only** the synthetic implementation, and the seam a real client would fill later
is the `ReferenceDataPort`/`CorporateActionsPort` `Protocol`s themselves — a real
`adapters/bloomberg/client.py` is a drop-in implementation of the same two ports, added by a later
spec once entitlements exist, with zero change to anything that consumes the ports.

Every consumer of the new contracts follows this repo's established additive-field discipline
(`specs/0006-mip-business-rules/`'s `z`/`n` blocks, `specs/0009-...`'s tier blocks,
`specs/0010-...`'s calendar-free settlement): a new **optional** input that is empty/absent by
default and produces byte-identical behavior when unused (NFR-001).

## Module layout

```text
src/inventory_optimizer/
├── domain/
│   ├── reference.py      # NEW — PointInTimeValue[T], SecurityReference, MarketCalendar, DataQuality
│   └── events.py         # NEW — CorporateActionEvent + version/lineage helpers
├── ports/
│   ├── reference_data.py     # NEW — ReferenceDataPort Protocol
│   └── corporate_actions.py  # NEW — CorporateActionsPort Protocol
├── enrichment/            # NEW package
│   ├── __init__.py
│   ├── point_in_time.py   # as-of resolution join (REQ-005, REQ-006)
│   └── security_master.py # reconciliation (REQ-007)
├── adapters/
│   └── bloomberg/          # NEW package — sole owner of vendor mnemonics
│       ├── __init__.py
│       ├── field_mapping.py    # versioned config loader (REQ-009)
│       ├── reference.py        # synthetic ReferenceDataPort impl (REQ-010)
│       └── corporate_actions.py # synthetic CorporateActionsPort impl (REQ-010)
├── validation/
│   └── reconciliation.py  # gains status/calendar checks (REQ-012, REQ-013)
├── settlement/
│   └── project.py          # gains optional calendar parameter (REQ-014)
├── formulation/
│   └── multi_period.py     # gains optional calendar parameter (REQ-014)
└── cli.py                  # gains the health-check surface (REQ-011)

configs/data_sources/           # NEW — example configuration, not runtime defaults
├── bloomberg.example.yaml
├── field_mapping.example.yaml
└── freshness_policy.yaml
```

`domain/lineage.py` and `domain/liquidity.py` from §22.2's full illustrative tree are **not**
created here — lineage is carried directly on `PointInTimeValue` (REQ-001) rather than a separate
module, and `liquidity.py` is R1 (`LiquidityEstimate` is out of scope). `ports/market_data.py`,
`ports/entity_data.py`, `ports/liquidity_data.py`, and `adapters/bloomberg/{pricing,funds,entities,
liquidity,events,client}.py` are likewise not created — they belong to R1 (T22-T24) and would be
unused, untested surface if added now.

## `PointInTimeValue[T]` (REQ-001, RISK-004)

Every other domain contract in this repo is a `pydantic.BaseModel` with
`model_config = ConfigDict(frozen=True, extra="forbid")`. Pydantic v2 supports generic models via
`pydantic.generics`-free `Generic[T]` inheritance directly (v2's native generic model support), so
this stays fully consistent with house style:

```python
from typing import Generic, TypeVar
from pydantic import AwareDatetime, BaseModel, ConfigDict

T = TypeVar("T")

class DataQuality(StrEnum):
    VERIFIED = "verified"
    ESTIMATED = "estimated"
    STALE = "stale"
    CONFLICTING = "conflicting"

class PointInTimeValue(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: T
    observed_at: AwareDatetime
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None
    source: str
    source_version: str
    field_mapping_version: str
    quality: DataQuality

    @model_validator(mode="after")
    def _check_interval(self) -> "PointInTimeValue[T]":
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self
```

`SecurityReference` and `MarketCalendar` are plain `BaseModel`s (not themselves generic) that get
*wrapped* in `PointInTimeValue[SecurityReference]` / `PointInTimeValue[MarketCalendar]` wherever
they flow through the system — the envelope is reusable, the payload types are not forced to know
about time.

```python
class SecurityReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    internal_security_id: str
    external_identifiers: Mapping[str, str]   # e.g. {"FIGI": "..."} — no mnemonic keys
    issuer_id: str
    share_class: str | None
    instrument_type: str
    primary_market: str
    currency: str
    country_of_risk: str
    trading_status: TradingStatus          # new StrEnum: ACTIVE, HALTED, SUSPENDED, DELISTED
    settlement_status: str | None
    lot_size: float | None
    tick_size: float | None

class MarketCalendar(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market: str
    currency: str
    trading_holidays: frozenset[date]
    settlement_holidays: frozenset[date]
    exceptional_closures: frozenset[date]

    def is_settlement_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self.settlement_holidays and day not in self.exceptional_closures
```

`external_identifiers` is a plain string-keyed mapping rather than named FIGI/CUSIP/ISIN fields —
deployment-specific identifier schemes vary, and REQ-008 already forbids vendor-specific keys from
appearing outside the adapter; a generic mapping keeps the contract from silently assuming Bloomberg
is the only source.

## `CorporateActionEvent` and versioning (REQ-004)

```python
class CorporateActionEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    version: int = Field(ge=1)
    supersedes_event_id: str | None   # points at the same event_id's prior version's own key, if any
    event_type: CorporateActionType    # new StrEnum: SPLIT, DIVIDEND, MERGER, SPINOFF, TENDER, ...
    status: CorporateActionStatus      # ANNOUNCED, CONFIRMED, AMENDED, CANCELLED
    affected_security_ids: tuple[str, ...]
    announcement_date: date
    effective_date: date | None
    record_date: date | None
    ex_date: date | None
    pay_date: date | None
    election_deadline: date | None
    terms: Mapping[str, str]
```

"Never mutated in place" (REQ-004) means exactly what every other append-only contract in this repo
already means: no method exists that changes an instance's fields; an amendment is modeled by
constructing a **new** `CorporateActionEvent` with the same `event_id`, `version = prior.version +
1`, and `status = AMENDED`. A repository/fixture keyed by `(event_id, version)` — not just
`event_id` — retains every version. `enrichment.point_in_time`'s resolution (below) is what picks
"the latest version known as of `known_as_of`" out of that set; no in-place field ever changes.

## As-of resolution (REQ-005, REQ-006)

```python
def resolve_latest_known(
    candidates: Iterable[PointInTimeValue[T]],
    *,
    as_of: datetime,
    known_as_of: datetime,
) -> PointInTimeValue[T] | None:
    eligible = [
        c for c in candidates
        if c.observed_at <= known_as_of
        and c.effective_from <= as_of
        and (c.effective_to is None or as_of < c.effective_to)
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda c: (c.effective_from, c.observed_at))
```

The `observed_at <= known_as_of` filter is the entire no-look-ahead guarantee (NFR-003): it is
applied before any effective-time reasoning, so a value can never be selected on the strength of
its economic correctness alone. For a **live** solve, callers pass `known_as_of = request.as_of`
(today's knowledge is today's knowledge); for a **backtest**, callers pass the simulated decision
time as `known_as_of` and the historical date being simulated as `as_of` — this is the "join on
both economic effective time and knowledge/observation time" §22.3 requires verbatim.
`CorporateActionEvent` resolution uses the same function with `(event_id)`-grouped candidates and
`version` as an `effective_from`-equivalent tiebreak (a higher version is never "more effective," it
is "more recently known" — both orderings agree in practice since amendments only arrive after
their predecessor, but the tie-break is `observed_at`, not `version`, to keep one honest rule).

## Security-master reconciliation (REQ-007)

```python
@dataclass(frozen=True, slots=True)
class ReconciliationConflict(Exception):
    field: str
    internal_value: object
    internal_source: str
    bloomberg_value: object
    bloomberg_source_version: str
```

`enrichment.security_master.reconcile(internal_id, internal_fields, reference)` compares a small,
explicit set of reconciled fields (currency, country_of_risk, instrument_type — the fields §9.2's
`SecurityInventory` already carries in some form) and raises `ReconciliationConflict` the first time
one disagrees, following `exceptions.InputValidationError`'s own philosophy of a structured,
named failure rather than an exit code or a logged warning. This mirrors §22.1's table row-by-row:
"If an internal and Bloomberg value conflict, the adapter emits a reconciliation exception or a
configured override record. It never silently chooses one." This spec ships the exception path
only; a configured-override path is a tracked follow-up (no desk need identified yet — see
`tasks.md`).

## Ports and the synthetic adapter (REQ-008, REQ-009, REQ-010)

```python
# ports/reference_data.py
@runtime_checkable
class ReferenceDataPort(Protocol):
    def get_security_reference(
        self, internal_security_id: str, *, as_of: datetime, known_as_of: datetime
    ) -> PointInTimeValue[SecurityReference] | None: ...

    def get_market_calendar(
        self, market: str, *, known_as_of: datetime
    ) -> PointInTimeValue[MarketCalendar] | None: ...

# ports/corporate_actions.py
@runtime_checkable
class CorporateActionsPort(Protocol):
    def get_events(
        self, security_id: str, *, known_as_of: datetime
    ) -> Sequence[CorporateActionEvent]: ...
```

`adapters/bloomberg/field_mapping.py` loads `configs/data_sources/field_mapping.example.yaml`
(schema: one entry per business concept, each naming its source mnemonic, unit, null policy, and
entitlement ID) into a frozen `FieldMapping` value carrying its own `version` string — this is the
`field_mapping_version` every `PointInTimeValue` REQ-001 requires. `adapters/bloomberg/reference.py`
and `corporate_actions.py` implement the two ports by reading an in-memory/fixture-file synthetic
dataset (hand-authored, versioned alongside the tests, never a captured real response — NFR-004)
through that mapping. Loading a mapping config is the *only* place a mnemonic-like string
(`"ID_BB_GLOBAL"`, `"PX_LAST"`) may legitimately appear in this repo's source, and only as
already-anonymized illustrative examples in the `.example.yaml` file, not real proprietary field
codes.

## Health check (REQ-011)

```python
def check_bloomberg_adapter_health(
    mapping: FieldMapping, adapter: ReferenceDataPort, *, sample_security_id: str, known_as_of: datetime
) -> BloombergHealthReport:
    ...
```

`BloombergHealthReport` (a small frozen model) carries, per configured concept: `mapped: bool`,
`entitlement_id: str`, `last_observed_at: datetime | None`, `available: bool`. Wired into `cli.py`
as a new `bloomberg-doctor` subcommand, following `_cmd_doctor`'s existing convention exactly
(catch every exception, report it as a check result, never let the process crash — `_cmd_doctor`'s
docstring already states this rule) rather than adding a Bloomberg branch to `_cmd_doctor` itself,
since the two check different things (environment/config vs. one specific vendor adapter) and a
firm without Bloomberg entitlements at all should not see Bloomberg-shaped output from its plain
`doctor` call.

## Validation wiring (REQ-012, REQ-013, REQ-014) — warnings, not hard failures

**Revised per the owner's 2026-09-14 decision.** These checks return `tuple[str, ...]` warnings,
following `scenarios.apply.apply_events`'s existing convention (accumulate a `list[str]`, return a
`tuple`) — not `ValidationIssue`/`InputValidationError`, which stays reserved for genuinely blocking
Section 9.8 invariants. Both live in `validation/reconciliation.py` as **new, optional keyword
parameters**, not new required inputs, and not a change to any existing function's positional
signature:

```python
def check_security_tradability(
    request: OptimizationRequest,
    references: Mapping[str, PointInTimeValue[SecurityReference]] = {},
) -> tuple[str, ...]:
    """REQ-012: a route with current_quantity_shares == 0 (the adopted, owner-flagged-uncertain
    V0 'new route' definition -- spec.md RISK-003) for a security whose resolved status is
    HALTED/SUSPENDED/DELISTED produces one warning naming the route and status. Absent
    `references`, always returns (). Never raises."""

def check_settlement_calendar(
    dates_and_markets: Sequence[tuple[date, str]],
    calendars: Mapping[str, MarketCalendar] = {},
) -> tuple[str, ...]:
    """REQ-013: one warning per (date, market) pair where `market` is present in `calendars` and
    the date is not `is_settlement_day`. Absent `calendars`, or for a market not present in it,
    always contributes no warning for that pair. Never raises."""
```

Callers:

- `facade.InventoryOptimizer.optimize()` gains `security_references: Mapping[str,
  PointInTimeValue[SecurityReference]] = {}` and (for symmetry, though REQ-014 is the multi-period
  path's own concern) no calendar parameter — a single-period `optimize()` call has no period dates
  to check beyond `request.as_of`, which `check_freshness` already covers. After the existing
  five-stage pipeline produces `result`, `optimize()` computes `extra_warnings =
  check_security_tradability(request, security_references)` and returns
  `result.model_copy(update={"warnings": result.warnings + extra_warnings})` when non-empty,
  otherwise `result` unchanged — zero cost, zero new object identity churn, when the mapping is
  empty (NFR-001).
- `settlement.project.project_multi_period` and `formulation.multi_period.solve_multi_period` each
  gain `calendars: Mapping[str, MarketCalendar] | None = None`. When `None` (the default), every
  period date is accepted exactly as `specs/0010-multi-period-settlement/` already does — the
  byte-identical path REQ-014/AC-007 require. When supplied, each period boundary date is checked
  via `check_settlement_calendar`, keyed by **currency** (recorded simplification: neither
  `SecurityInventory` nor `LoanRoute` carries a "market" field today, only `currency`; a real
  market/calendar key can replace this once `SecurityReference.primary_market` enrichment is
  actually threaded through these two modules, which this spec does not attempt — that is a bigger
  change than REQ-014's scope), and the resulting warnings are appended to the already-existing
  `warnings` accumulation each module already threads through to its `MultiPeriodProjection`
  (`project_multi_period`'s existing `all_warnings` list; `solve_multi_period`'s
  `_build_projection`, which currently hard-codes `warnings=()` and gains the same accumulation).

## Constitution Check

- **Spec is the source of truth:** every REQ/NFR traces to `01_SPEC.md` §22.2-§22.4, §22.8 (timing
  only), and `00_PLAN.md`'s Bloomberg workstream steps 1-2. No code precedes this document.
- **No orphan code:** every new module is cited by a REQ below; no speculative
  `ports/market_data.py`-style file for a concept this slice does not use.
- **Correct by construction — no look-ahead:** REQ-005/REQ-006/NFR-003 make this the spec's central
  guarantee, tested directly (AC-001).
- **No silent trade-offs:** the synthetic-only-adapter decision, the "new route" definition, and the
  hard-fail-vs-warning choice for calendar violations are each raised as open questions rather than
  decided silently, per `spec.md`'s Assumptions & Open Questions.
- **Reversibility:** every new field/parameter is optional and defaults to today's behavior
  (NFR-001); nothing here is a breaking change to an existing contract.

## Traceability Matrix

| Requirement | Plan section | Test(s) (see `tasks.md`) |
| --- | --- | --- |
| REQ-001 | `PointInTimeValue[T]` | `test_domain_reference.py` |
| REQ-002 | `SecurityReference` | `test_domain_reference.py` |
| REQ-003 | `MarketCalendar` | `test_domain_reference.py` |
| REQ-004 | `CorporateActionEvent` versioning | `test_domain_events.py` |
| REQ-005 | As-of resolution | `test_point_in_time.py` |
| REQ-006 | As-of resolution (no-look-ahead) | `test_point_in_time.py` |
| REQ-007 | Security-master reconciliation | `test_security_master.py` |
| REQ-008 | Ports | `test_architecture_boundaries.py` |
| REQ-009 | Field mapping | `test_field_mapping.py` |
| REQ-010 | Synthetic adapter | `test_bloomberg_adapter.py` |
| REQ-011 | Health check | `test_bloomberg_doctor.py` |
| REQ-012 | Tradability validation | `test_reconciliation_bloomberg.py` |
| REQ-013 | Calendar validation | `test_reconciliation_bloomberg.py` |
| REQ-014 | Multi-period calendar wiring | `test_multi_period_lp_compiler.py` additions, `test_settlement_project.py` additions |
| REQ-015 | Golden/property tests | `test_point_in_time.py`, `test_domain_events.py` |
| NFR-001 | Byte-identical when absent | full suite regression run; `test_multi_period_lp.py`/`test_settlement_project.py` unchanged |
| NFR-002 | No mnemonic leak | `test_architecture_boundaries.py` |
| NFR-003 | No look-ahead | `test_point_in_time.py` |
| NFR-004 | Synthetic fixtures only | fixture review (manual, recorded in PR description) |
| NFR-005 | No credential exposure | `test_bloomberg_doctor.py` |

## Trade-offs & Alternatives

- **Generic `PointInTimeValue[T]` vs. one concrete class per concept.** A concrete
  `SecurityReferenceRecord`/`MarketCalendarRecord`/etc. per concept would avoid any generic-model
  subtlety but would duplicate the identical seven-field envelope four times and drift over time.
  The generic form costs one `TypeVar` and a shared validator; chosen.
- **Exception-only reconciliation vs. exception-or-override (REQ-007).** §22.1 sanctions both
  ("emits a reconciliation exception or a configured override record"). This spec ships only the
  exception path because no desk has asked for an override policy yet, and inventing one now would
  be exactly the kind of undocumented policy the constitution forbids ("a preference must not be
  disguised as a hard rule" — §22.16's own constraint-inclusion rule 2, applied here to data
  policy rather than a model constraint). Tracked as a follow-up.
- **Hard-fail calendar/status validation vs. a warning.** **Resolved by the owner (2026-09-14):
  warnings.** This departs from this repo's usual fail-closed default for validation, but correctly
  reflects that today's calendars/statuses are entirely synthetic fixtures, not real market data —
  hard-failing on unreviewed fixture data would be a worse default than surfacing it for review. A
  later spec, once real data backs these checks, may promote either to a hard failure.

## Validation Strategy

1. Full existing suite (`pytest tests/ -q`, 275 passed/2 skipped baseline) must stay green
   throughout — run after every task, not just at the end.
2. `specs/0010-multi-period-settlement/`'s existing tests (`tests/golden/test_multi_period_lp.py`,
   `tests/unit/test_multi_period_lp_compiler.py`, `tests/unit/test_settlement_project.py` if it
   exists, or wherever Phase 1/2 tests live) must pass **unchanged** before any new calendar test is
   added — the regression gate for RISK-002.
3. New unit tests for each domain contract's validators (interval ordering, version monotonicity).
4. Property test: for any two `PointInTimeValue`s of the same concept with different `observed_at`,
   resolving with `known_as_of` between them always returns the earlier one — a `hypothesis`-based
   test following `tests/property/test_lp_properties.py`'s existing precedent (§24.2).
5. A static/architecture-boundary test enumerating known Bloomberg mnemonic strings from
   `01_SPEC.md`'s own text (e.g. anything matching common Bloomberg field-name conventions) and
   asserting none appears outside `adapters/bloomberg/` (NFR-002) — mirroring
   `test_architecture_boundaries.py`'s existing `highspy`/`pandas` isolation checks.
6. Manual fixture review recorded in the implementation PR description: every JSON/YAML fixture
   added is hand-authored, not derived from a real Bloomberg terminal/API response (NFR-004).

### Worked fixture sketch (for the golden tests)

A security `SEC-HALT-1` with two `SecurityReference` versions: `observed_at=2026-01-01` (status
`ACTIVE`) and `observed_at=2026-01-10` (status `HALTED`). Resolving with `known_as_of=2026-01-05`
must return the `ACTIVE` version even though `HALTED` is "more true" by 2026-01-10 — proving
REQ-006/NFR-003 concretely, and giving AC-001 a fixture that fails obviously (returns `HALTED`) if
the look-ahead guard is ever removed by accident.

## Rollout, Observability & Rollback

- Purely additive: no existing config, request, or CLI flag changes shape. Rollback is deleting the
  new modules and the two new optional parameters — no migration needed.
- `bloomberg-doctor`'s output is read-only and side-effect-free, safe to run in any environment
  including one with zero Bloomberg configuration (it reports "no mapping configured" rather than
  erroring).
- No new runtime dependency: the synthetic adapter needs nothing beyond what `pyproject.toml`
  already pins (Pydantic, stdlib `datetime`/`pathlib`). A real adapter's future SDK dependency is
  explicitly deferred, so this spec adds no new optional extra.

## Open Questions

All three resolved by the owner (2026-09-14) — see `spec.md`'s Assumptions & Open Questions for the
resolutions. Question 2 (the "new route" definition) is resolved *pragmatically* (a V0 default
adopted despite genuine uncertainty), not fully settled; `spec.md`'s RISK-003 tracks it as a named
follow-up rather than closed knowledge.
