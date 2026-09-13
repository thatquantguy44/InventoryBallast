# Spec: Bloomberg data foundation (Realism release R0 — point-in-time reference, calendars, corporate-action lineage)

- **ID:** 0011-bloomberg-data-foundation
- **Status:** Proposed — pending owner review (see Assumptions & Open Questions; not yet approved for implementation)
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code)
- **Approver:** pending
- **Last updated:** 2026-09-14

> WHAT and WHY only. No implementation detail — that belongs in `plan.md`.

## Problem & Context

`01_SPEC.md` §22 ("Bloomberg-Enriched Realism and Model Extensions") and `00_PLAN.md`'s "Bloomberg-
enriched realism workstream" are entirely unbuilt — `docs/handoff.md` names this, alongside the
agency/prime desk track, as one of the two remaining workstreams after Phase 5, and explicitly says
neither has a `specs/NNNN-*` directory yet. The owner has now directed that this workstream start
(2026-09-14). This spec scopes its first slice.

**Why this slice, not a bigger one.** `01_SPEC.md` §22.15's priority table calls P1 (expected
economics — take-up, survival, liquidity costs) "the recommended first realism release," but
`01_SPEC.md` §26's own Implementation Task Matrix makes that impossible to build first: T22-T24
(the tasks that "form R1") each depend on T19 and/or T20. **T19-T21 — which "form required realism
release R0" — are a hard prerequisite of every later realism task, not merely a recommended
starting point.** `00_PLAN.md` states plainly: "R0 is required before production use." This spec is
exactly T19-T21:

- **T19** — point-in-time lineage/reference contracts (§22.3).
- **T20** — Bloomberg ports, field mappings, and adapter health check (§22.2, §22.4).
- **T21** — calendars, security status, and corporate-action *timing* wired into bounds/scenarios
  (§22.4's table: "LP bounds/RHS" and "LP scenario bounds", not new objective terms).

Every item this spec builds is explicitly "Validation only," "LP bounds/RHS," or "Data
architecture" impact per §22.15's own P0 row — none of it touches the objective function, none of
it estimates a coefficient, and none of it requires model-risk calibration evidence. That is a
deliberate scope boundary, not an oversight: §22.5's realistic economic coefficients (take-up,
survival, liquidity cost, etc.) each "carry model version, calibration date, [and] uncertainty," and
none of that exists yet. Building R1 (T22-T24) before R0 exists would mean either inventing those
coefficients without a data foundation to source them from, or hard-coding placeholder economics —
exactly what §22.1's source-of-truth table and this repo's own constitution ("no silent trade-offs")
forbid.

**This is not the DocumentRefinery/collateral-schedule track.** `docs/handoff.md`'s "Possible spec
idea: schedules/collateral (T29-T32) via DocumentRefinery" section is a separate, unrelated
workstream (eligibility/collateral/CSA documents, T29-T32) blocked on a sibling repo's own
maturity. This spec is Bloomberg *reference/market* data (security identity, calendars, corporate
actions) for the core optimizer, not eligibility/collateral schedules. The two may eventually share
the bitemporal/point-in-time pattern this spec introduces, but neither depends on the other.

**No real Bloomberg entitlement exists in this environment.** `01_SPEC.md` §22.1 says explicitly:
"entitlements and precise available fields must be confirmed in the firm's data catalog before
implementation." This repo has no Bloomberg API package (`blpapi` or equivalent), no credentials,
and no confirmed field catalog. §22.2 already anticipates this: "Tests use synthetic responses and
never redistribute proprietary payloads." This spec therefore builds the full port/contract/
adapter-boundary architecture plus a **synthetic, fixture-backed adapter** satisfying those ports —
enough to validate the whole data model and wire it into the optimizer end to end — and explicitly
defers a real vendor-SDK-backed adapter as a follow-up pending the firm's actual entitlement
confirmation (see Non-Goals and Assumptions & Open Questions).

## Goals

- Add the point-in-time contracts §22.3 requires for this slice: a generic `PointInTimeValue[T]`
  envelope (`observed_at`, `effective_from`, `effective_to`, `source`, `source_version`,
  `field_mapping_version`, `quality`), `SecurityReference`, `MarketCalendar`, and
  `CorporateActionEvent`. (§22.3's `EntityRelationship`, `MarketState`, `LiquidityEstimate`, and
  `FundHolding` are R1+ concepts and are explicit Non-Goals here.)
- Add the two ports this slice needs (`ports/reference_data.py`, `ports/corporate_actions.py`) as
  narrow business-concept `Protocol`s carrying no vendor mnemonics, per §22.2's adapter-boundary
  rule. (`ports/market_data.py`, `ports/entity_data.py`, `ports/liquidity_data.py` are R1+ and out
  of scope.)
- Add the Bloomberg adapter boundary package (`adapters/bloomberg/`) with a versioned,
  configuration-driven `field_mapping.py` (unit conversion, null policy, effective-time semantics,
  entitlement identifier — §22.2) and a synthetic, fixture-backed implementation of the two R0
  ports for tests and local development. No network client, no vendor SDK dependency.
- Add `enrichment/point_in_time.py`: the as-of resolution join that returns the latest value known
  at a given observation time and effective at a given economic time, honoring §22.3's rule that
  "a corporate action correction received tomorrow must not appear in yesterday's simulated
  decision."
- Add `enrichment/security_master.py`: reconciliation between the optimizer's existing internal
  security identifiers (`SecurityInventory.security_id`, `LoanRoute` references) and
  `SecurityReference`, emitting a structured reconciliation exception on conflict rather than
  silently choosing a value, per §22.1's source-of-truth table.
- Wire calendar and security-status enrichment into pre-solve validation and scenario/settlement
  date checks — **strictly additive and opt-in**: a request that supplies no enrichment behaves
  byte-identically to today (the same zero-cost-when-absent property every prior spec in this repo
  has held for its own new optional field).
- Close the gap `specs/0010-multi-period-settlement/`'s own handoff note names explicitly: "no
  calendar port exists anywhere in this repo... every `planning_periods` date is treated as a valid
  settlement day." Wire the new `MarketCalendar` port into `settlement/project.py` and
  `formulation/multi_period.py`, opt-in, so `0010`'s existing behavior (and all its existing tests)
  is unchanged when no calendar is supplied.
- Add an adapter health-check surface satisfying §22.4's requirement: list required business
  concepts, mapped fields, entitlement identifiers, last successful observation, and unavailable
  optional concepts, **without ever exposing credentials**.
- Add example configuration files (`configs/data_sources/bloomberg.example.yaml`,
  `field_mapping.example.yaml`, `freshness_policy.yaml`) per §22.2's project structure.
- Add bitemporal/no-look-ahead golden tests (the acceptance evidence T19/T21 require) and confirm
  every fixture is synthetic (DAT-006).

## Non-Goals

- **A real Bloomberg-SDK-backed adapter.** Requires the firm's actual entitlements and confirmed
  field catalog (§22.1) — neither exists in this repository or its execution environment. The
  synthetic adapter this spec builds is the complete deliverable; a real client is a tracked
  follow-up (see `plan.md`/`tasks.md`).
- **R1 economics (T22-T24):** legal-entity hierarchy aggregation, take-up/survival/repricing
  hazards, dynamic liquidity buffers, and any new objective coefficient. Nothing in this spec adds,
  removes, or reweights a term in the LP/MIP/QP objective.
- **Full corporate-action economics (§22.8's cash-flow/quantity-transformation/election
  handling).** This spec models `CorporateActionEvent` as a point-in-time contract and validates
  timing/tradability consistency (T21's own scope: "LP bounds/RHS"); manufactured-payment cost,
  quantity transformation, and MIP election handling are R1+/T21's own follow-on and explicitly
  deferred.
- **`MarketState` (price/FX/volume/spread/volatility), `LiquidityEstimate`, `FundHolding`,
  event/regime features (§22.13).** All R1+.
- **Entity hierarchy aggregation, censoring-aware elasticity, robust/CVaR scenarios, multi-market
  fungibility/transformation graphs.** R1-R3, untouched.
- **Eligibility/collateral schedules (T29-T32).** A separate workstream (`docs/handoff.md`'s
  DocumentRefinery section); not this spec's concern.
- **A CLI subcommand for anything beyond the health check.** No new `optimize`/`scenarios` flags;
  the enrichment inputs this spec adds are new, optional fields on existing request-adjacent
  contracts, not new top-level CLI surface.

## Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| REQ-001 | The system shall provide a generic, frozen `PointInTimeValue[T]` contract carrying `value`, `observed_at`, `effective_from`, `effective_to`, `source`, `source_version`, `field_mapping_version`, and `quality` (a new `DataQuality` enum: at minimum `VERIFIED`, `ESTIMATED`, `STALE`, `CONFLICTING`). | must |
| REQ-002 | The system shall provide a `SecurityReference` contract (canonical internal ID, external identifier(s), issuer ID, share class, instrument type, primary market, currency, country of risk, trading/settlement status, lot/tick conventions, effective interval), wrapped in `PointInTimeValue`. | must |
| REQ-003 | The system shall provide a `MarketCalendar` contract (market, currency, trading/settlement date predicates, cutoffs, exceptional closures) and a resolver function answering "is this date a valid trading/settlement day for this market" as of a given knowledge time. | must |
| REQ-004 | The system shall provide a `CorporateActionEvent` contract (event ID/type/status, announcement/updated/effective/record/ex/pay dates, affected security IDs, terms, election deadline) that is never mutated in place: an amendment or cancellation creates a new version referencing the prior one, preserving history per §22.3/§22.8. | must |
| REQ-005 | `enrichment.point_in_time` shall resolve, for a given `(concept, as_of, known_as_of)` query, the latest `PointInTimeValue` whose `effective_from <= as_of <= (effective_to or +inf)` and `observed_at <= known_as_of`, returning nothing (not a stale silent default) when no such value exists. | must |
| REQ-006 | `enrichment.point_in_time`'s resolution shall never return a value observed after `known_as_of`, even if it is the economically correct value for `as_of` — preventing exactly the look-ahead §22.3 names ("a corporate action correction received tomorrow must not appear in yesterday's simulated decision"). | must |
| REQ-007 | `enrichment.security_master` shall reconcile an internal security identifier against a `SecurityReference` and raise a structured `ReconciliationConflict` (naming both values and their sources) when they disagree on a reconciled field, rather than silently preferring either. | must |
| REQ-008 | The system shall add `ports.reference_data.ReferenceDataPort` and `ports.corporate_actions.CorporateActionsPort` as `Protocol`s expressed entirely in business-concept types (`SecurityReference`, `MarketCalendar`, `CorporateActionEvent`); no Bloomberg field mnemonic may appear outside `adapters/bloomberg/`. | must |
| REQ-009 | `adapters.bloomberg.field_mapping` shall load a versioned mapping configuration (mnemonic → business concept, unit conversion, null policy, effective-time semantics, entitlement identifier) from a YAML file matching `configs/data_sources/field_mapping.example.yaml`'s schema, and shall record the loaded mapping's own version on every value it produces. | must |
| REQ-010 | The system shall provide a synthetic, fixture-backed implementation of both R0 ports (`adapters.bloomberg`) requiring no network access, no vendor SDK, and no credentials, usable directly in tests and local development. | must |
| REQ-011 | The system shall provide a health-check function reporting, per configured business concept: whether it is mapped, its entitlement identifier, the last successful observation time (if any), and whether it is currently unavailable — and shall never include a credential, API key, or raw vendor payload in its output. | must |
| REQ-012 | When an `OptimizationRequest`'s inventory or routes reference a security whose resolved `SecurityReference` status (as of the request's `as_of`) is halted, suspended, or delisted, validation shall reject any *new* route for that security with a structured issue, while leaving requests that supply no `SecurityReference` for that security completely unaffected. | must |
| REQ-013 | When a `MarketCalendar` is supplied for a market referenced by a scenario's trade event or a multi-period request's period date, validation/compilation shall reject a settlement date that is not a valid settlement day for that market, while leaving requests/scenarios that supply no calendar completely unaffected. | must |
| REQ-014 | `settlement.project.project_multi_period` and `formulation.multi_period` shall accept an optional `MarketCalendar` mapping and use it to validate each period's date, falling back to today's unchecked-date behavior exactly (byte-for-byte) when none is supplied. | must |
| REQ-015 | The system shall provide golden/property tests demonstrating: (a) a future-dated `PointInTimeValue`/`CorporateActionEvent` correction is invisible to a resolution query whose `known_as_of` predates it; (b) an amended/cancelled `CorporateActionEvent` preserves its prior version rather than overwriting it; (c) every fixture used is synthetic, containing no real vendor field names copied from Bloomberg documentation beyond what §22.3/§22.4 already name generically in the spec text. | must |

## Non-Functional Requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | Zero behavior change when no enrichment is supplied | Every existing test (275 pre-this-spec) continues to pass unchanged; an `OptimizationRequest`/scenario/multi-period request with no `SecurityReference`/`MarketCalendar` compiles to byte-identical variables, rows, and results. |
| NFR-002 | No vendor mnemonic leaks past the adapter boundary | `tests/unit/test_architecture_boundaries.py` gains a check that no module outside `adapters/bloomberg/` references a raw Bloomberg field mnemonic string (matching how it already isolates `highspy`/`pandas`). |
| NFR-003 | No look-ahead | Every point-in-time resolution is provably a function of `known_as_of`; no code path can observe a value whose `observed_at` is after the caller's declared knowledge time. |
| NFR-004 | No proprietary payloads | All test fixtures are synthetic and hand-authored; none is copied from a real Bloomberg response (DAT-006). |
| NFR-005 | No credential exposure | The health-check output and every log/audit event this spec adds contain no API key, session token, or entitlement secret — only identifiers and booleans. |

## Acceptance Criteria

| ID | Given / When / Then | Covers |
| --- | --- | --- |
| AC-001 | Given a `PointInTimeValue` with `observed_at` after a query's `known_as_of`, when `enrichment.point_in_time` resolves that concept, then the future value is not returned (an earlier value is returned, or nothing). | REQ-005, REQ-006, NFR-003 |
| AC-002 | Given a `CorporateActionEvent` amended twice, when the version history is inspected, then all three versions (original plus two amendments) are retrievable and none has been overwritten. | REQ-004, REQ-015 |
| AC-003 | Given an internal security identifier and a conflicting `SecurityReference` field, when `enrichment.security_master` reconciles them, then a `ReconciliationConflict` is raised naming both values and sources, and no field is silently overridden. | REQ-007 |
| AC-004 | Given a request that supplies no `SecurityReference`/`MarketCalendar`/`CorporateActionEvent` at all, when compiled and solved, then the result is byte-identical to the same request run against pre-this-spec code. | NFR-001 |
| AC-005 | Given a security whose resolved status is `HALTED` as of the request's `as_of`, when a new route for that security is validated, then validation raises a structured issue naming the security and its status, and existing routes for other securities are unaffected. | REQ-012 |
| AC-006 | Given a scenario trade event whose settlement date falls on a day the supplied `MarketCalendar` marks as a market holiday, when the scenario is applied, then it is rejected with a structured issue rather than silently proceeding. | REQ-013 |
| AC-007 | Given a multi-period request with a supplied calendar and a period landing on an invalid settlement day, when `project_multi_period`/the joint multi-period LP compiles, then it fails closed with a structured issue; given the same request with no calendar supplied, then it behaves exactly as `specs/0010-multi-period-settlement/`'s existing tests already verify. | REQ-014, NFR-001 |
| AC-008 | Given the synthetic Bloomberg adapter and a field-mapping config, when the health check runs, then it reports each configured concept's mapped/unmapped state, entitlement identifier, and last observation time, and the output contains no string matching a credential/key pattern. | REQ-011, NFR-005 |
| AC-009 | Given a mapping config bumped to a new `field_mapping_version`, when a value is produced through it, then the value's `field_mapping_version` reflects the new version, and a value produced under the old config retains the old version (no retroactive rewrite). | REQ-009 |
| AC-010 | Given the full existing test suite (275 tests, 2 skipped), when run after this spec's changes with no enrichment supplied anywhere, then all still pass unchanged. | NFR-001 |
| AC-011 | Given a grep of every file outside `adapters/bloomberg/`, when scanned for known Bloomberg field mnemonics (e.g. `PX_LAST`, `ID_BB_GLOBAL`), then none is found. | REQ-008, NFR-002 |

## Data & Dependencies

- `domain/reference.py` (new): `PointInTimeValue[T]`, `SecurityReference`, `MarketCalendar`,
  `DataQuality`.
- `domain/events.py` (new): `CorporateActionEvent` and its versioning/lineage helpers.
- `ports/reference_data.py`, `ports/corporate_actions.py` (new): the two R0 `Protocol`s, following
  the existing `ports/` convention (`ports/solver.py`, `ports/demand.py`) of business-concept-only
  types and no concrete backend imports.
- `adapters/bloomberg/` (new package): `field_mapping.py`, `reference.py`, `corporate_actions.py`,
  and the synthetic fixture data backing them — following `adapters/dataframe.py`'s established
  pattern of being the sole owner of an optional/external dependency (here: the *absence* of one,
  since no real vendor SDK exists to import yet).
- `enrichment/` (new package): `point_in_time.py`, `security_master.py`.
- `configs/data_sources/` (new): `bloomberg.example.yaml`, `field_mapping.example.yaml`,
  `freshness_policy.yaml` — example configuration only, not runtime defaults.
- `validation/` (existing package): gains the opt-in status/calendar checks (REQ-012, REQ-013),
  following `validation/reconciliation.py`'s existing structured-`ValidationIssue` convention.
- `settlement/project.py`, `formulation/multi_period.py` (existing, from
  `specs/0010-multi-period-settlement/`): gain an optional calendar parameter (REQ-014), with the
  no-calendar path required to stay byte-identical to `0010`'s own tests.
- `cli.py` (existing): gains the health-check surface (REQ-011) — extending `_cmd_doctor`'s
  existing pattern or adding one new subcommand, decided in `plan.md`.
- `specs/engine_spec/TRACEABILITY.md` rows `DAT-001` through `DAT-006` — this spec's evidence
  target (left `SPECIFIED` in this document; updated only once implementation lands, per T09/T10's
  precedent in `specs/0009-discrete-fee-tier-pricing/tasks.md`).

## Risks

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| RISK-001 | Building only a synthetic adapter could be mistaken for "Bloomberg integration is done" when no real vendor connection exists. | A desk could believe R0 delivers live data when it delivers only the architecture and a fixture-backed stand-in. | Every acceptance criterion and this spec's own status ("Proposed") state the synthetic scope explicitly; `tasks.md`'s Follow-ups names the real-adapter work as separately gated on entitlement confirmation, matching §22.1's own text almost verbatim. |
| RISK-002 | Wiring an optional calendar into `settlement/project.py`/`formulation/multi_period.py` touches code `specs/0010-multi-period-settlement/` already shipped and tested. | A careless change could regress 0010's 35 existing tests. | REQ-014/AC-007 require the no-calendar path to be byte-identical; `plan.md`'s Validation Strategy runs 0010's full existing suite unchanged as a regression gate before any new calendar test is added. |
| RISK-003 | A hard-fail-closed rule for halted/suspended securities (REQ-012) could reject a legitimate desk workflow (e.g. recalling shares of a halted security, which is not "a new route"). | Over-broad validation could block a valid recall/exit action. | REQ-012 is scoped narrowly to *new* routes only; recalls/returns/sells of an already-existing route are untouched. Flagged explicitly in Assumptions & Open Questions for owner confirmation before implementation, since "new route" needs a precise definition against existing route-state fields. |
| RISK-004 | `PointInTimeValue[T]` as a generic Pydantic model may need care to stay `frozen=True`/`extra="forbid"` consistent with every other domain contract while remaining genuinely generic over `T`. | Getting this wrong could force a less type-safe design (e.g. `Any`) that undermines the whole point-in-time contract. | `plan.md` resolves the exact Pydantic generic-model pattern before any dependent contract is written; this is a mechanical HOW question, not a design judgment call, so it does not block spec approval. |

## Assumptions & Open Questions

- **Open question (needs owner sign-off before implementation):** is a fully synthetic adapter —
  with no real Bloomberg SDK call anywhere in this repo — an acceptable complete deliverable for
  this spec, given `01_SPEC.md` §22.1's explicit statement that real entitlements/field catalogs
  must be confirmed first? This spec assumes yes, and defers the real client as a tracked
  follow-up. If the owner instead wants to pursue real entitlement confirmation now, that changes
  this spec's scope materially (it would need a data-catalog input this repo does not have).
- **Open question (needs owner sign-off):** REQ-012's precise definition of "new route" for a
  halted/suspended/delisted security. Candidate definition: any route whose
  `current_quantity_shares` is `0` in the incoming request (i.e., genuinely new exposure), leaving
  any route with existing quantity free to be reduced, recalled, or sold. Confirm before
  implementation, since getting this wrong either under- or over-blocks a real desk action.
- **Open question (needs owner sign-off):** should REQ-013's calendar check be a hard validation
  failure (reject the whole request/scenario) or a warning surfaced in the result, for a first
  release with no real calendar data behind it (only synthetic fixtures)? This spec assumes hard
  failure, matching the engineering-principles rule against silent approximation, but the owner may
  prefer a softer rollout given today's calendars are entirely synthetic.
- Assumption: `EntityRelationship`, `MarketState`, `LiquidityEstimate`, and `FundHolding` (§22.3)
  are correctly excluded from R0 because no R0 task in `01_SPEC.md` §26 needs them (T19-T21's own
  acceptance evidence never references entity/price/liquidity/fund concepts) — they first appear as
  T22-T24 dependencies.
- Assumption: this spec's `DataQuality` enum values are a minimal starting set (`VERIFIED`,
  `ESTIMATED`, `STALE`, `CONFLICTING`); §22.1's table implies more granularity may be needed once a
  real adapter exists (e.g. `UNENTITLED`, `FUTURE_EFFECTIVE`) — additive later, not blocking now.

## Exceptions

None recorded.
