# Spec: Scenario engine and basic stress testing (T13-T14)

- **ID:** 0004-scenario-engine
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted and implemented by Claude Code)
- **Approver:** Joshua Lutkemuller, CFA (asked to work on T13/T14; approved via implementation review)
- **Last updated:** 2026-09-05

> WHAT and WHY only. No implementation detail — that belongs in `plan.md`.

## Problem & Context

`specs/engine_spec/01_SPEC.md` §13 defines trade and what-if scenarios: typed overlays (trade events,
rate/demand/inventory shocks, policy overrides, schedule overlays, collateral shocks, desk events)
applied to an immutable clone of the baseline request, re-solved, and compared against the
already-computed baseline result. `specs/engine_spec/ROADMAPS.md`'s release-gate table names this
plainly: **R2 | Trade and shock scenarios | T13-T14 | R1 | Batch equals isolated solves; baseline
stays immutable.** Nothing under `src/inventory_optimizer/` builds any of this yet — no
`Scenario`/`TradeEvent` type exists, `services.ScenarioService` was deliberately left undefined by
T12 (`specs/0003-public-api-cli/spec.md`'s Non-Goals), and the CLI's `scenarios` subcommand only
prints a "not implemented" message.

§13's full model is much larger than what this repo can honestly build today: `schedule_overlays`
need the eligibility-schedule compiler (T29, not started), `collateral_shocks` need the collateral
mode (T30-T32, not started), and `desk_events` need the agency/prime desk profiles (T35-T39, not
started) — `specs/engine_spec/TRACEABILITY.md`'s own `SCN-004` row already tags desk events `T40`, not
`T13-T14`. This spec builds the slice that R2's own exit gate actually requires and that today's
domain contracts already support: typed trade events (§13.1's seven types, in full), rate and
demand shocks, the overlay/compare/batch pipeline, and `ScenarioComparison` reporting — deferring
everything that needs an unbuilt subsystem, the same way T11 deferred 21 of 24 reason codes and
T12 deferred `ScenarioService`'s definition until now.

Two worked examples ground this spec, both already in `specs/engine_spec/EXAMPLES.md`:

- **E2 (Fee Elasticity Shock)** is, on inspection, a `RateShock` scenario: "the baseline
  request/hash is unchanged after the scenario" and "batch and isolated scenario results agree
  within tolerance" are literally `SCN-001`/`SCN-003`'s own wording.
  `reporting.explanations.explain_routes` already derives `ELASTICITY_REDUCED_DEMAND` from
  `context.demand_caps[...].reason_code` (T06/T11) — applying a rate shock and re-running the
  existing `InventoryOptimizer.optimize()` pipeline reproduces this with **no changes to
  `reporting/`** at all, since demand caps are recomputed fresh from whatever `fee_rate` a route
  carries at compile time.
- **E3 (Proposed Sale and Recall Feasibility)** is a `TradeEvent` (`SELL`) scenario, with both a
  feasible variant (the LP redistributes: `q_A=70`, `q_B=0` after a 30-share sale drops
  `total_lendable_shares` from 100 to 70) and an infeasible variant (a hard post-state minimum on
  Route A conflicts with the reduced supply). Both are reproducible exactly by adjusting only
  `total_lendable_shares` and leaving routes' `current_quantity_shares` untouched — the LP's own
  `inventory_balance` row and `TransitionIdentityConstraint` (already implemented, T08) do the rest;
  see `plan.md`'s "Reconciling a sale against an existing book" for the load-bearing design decision
  this depends on.

**Added at the user's request, beyond §13's own text:** a small, additive "basic stress testing"
capability — running a batch of (typically adverse) scenarios and summarizing worst-case
degradation in one report, built as a thin layer over the same batch-execution machinery `SCN-003`
already requires. This is not part of `01_SPEC.md`'s normative text, so it gets no
`specs/engine_spec/TRACEABILITY.md` row of its own (that document stays faithful to the copied
upstream spec) — it is tracked only by this spec's own `REQ-*`/`AC-*` IDs.

## Goals

- `Scenario`/`TradeEvent`/`RateShock`/`DemandShock` domain models (§13.1's seven `TradeEvent` types
  in full; `rate_shocks`/`demand_shocks` scoped to route-fee and demand-forecast overrides).
- `apply_scenario(baseline, scenario) -> (OptimizationRequest, warnings)`: clones the baseline immutably,
  applies only timing-gated-effective trade events (§13.2) in a deterministic order (§13.3 steps
  1-5), and never mutates the input (`SCN-001`).
- `run_scenario(baseline_result, baseline_request, scenario, optimizer) -> ScenarioComparison`:
  re-validates, re-solves, and produces the §13.4 comparison output (scoped to what's computable
  from today's `OptimizationResult` — see Non-Goals).
- `run_scenarios(...) -> tuple[ScenarioComparison, ...]`: batch execution that is provably
  equivalent to calling `run_scenario` once per scenario (`SCN-003`).
- `services.ScenarioService` (finally defined, per T12's deferral) + a concrete implementation the
  facade/CLI use.
- A real `inventory-optimizer scenarios` CLI subcommand: one scenario file → one comparison; a
  batch file → a batch of comparisons.
- `run_stress_test(baseline_result, baseline_request, scenarios, optimizer) -> StressTestReport`:
  the additive stress-testing capability above.

## Non-Goals

- **`schedule_overlays`, `collateral_shocks`, `desk_events`** (§13.1) — need T29 (eligibility
  schedules), T30-T32 (collateral mode), and T35-T39 (agency/prime desk profiles) respectively,
  none of which exist. `Scenario` does not declare these fields at all rather than declaring
  untestable stubs (the same reasoning T12 applied to `ScenarioService` itself).
- **`InventoryShock` and `PolicyOverride`** — neither has a concrete field shape anywhere in
  `01_SPEC.md` or `DICTIONARY.md` beyond a name, and neither is exercised by any worked example.
  Deferred until a real caller need or worked example pins their shape down.
- **Schedule-version-aware event application** (§13.2's "schedule versions are selected using both
  scenario effective time and request observation time") — no schedule subsystem exists (T29);
  event timing here uses only `effective_date <= request.effective_date`, a calendar/holiday-naive
  comparison (`T21`'s corporate-action/settlement-calendar realism is separately tracked and not
  attempted here, matching `SCN-002`'s own `T13, T21` task tag).
- **Agency/prime-specific comparison fields** (§13.4's "agency owner/mandate/indemnification/
  fairness deltas or prime client/source/... deltas") — no agency/prime desk profile exists yet
  (T35-T40).
- **Per-route dollar attribution for every objective component** — `EconomicsSummary` (T11) is
  per-component, not per-route. `ScenarioComparison` computes a per-route economic delta only for
  routes tagged `TRADE_REDUCED_SUPPLY`, reusing `fee_revenue_coefficient` directly (the same
  function `reporting.explanations` already reuses) rather than inventing a new per-route
  attribution system.
- **Infeasibility repair/diagnostics** (§19) — a scenario that solves to `INFEASIBLE` reports that
  status plainly (`ScenarioComparison.status`); it does not attempt repair-mode relaxation or
  produce the richer diagnostic fields §19.2 describes (still `SPECIFIED`, untouched).
- **Warm-start / shared-model reuse for batch execution** — `00_PLAN.md`'s Phase 2 item 3 says
  "safe model reuse or warm starts **where supported**"; `run_scenarios` here calls
  `InventoryOptimizer.optimize()` fresh per scenario. This is a performance follow-up, not a
  correctness gap — `SCN-003` only requires batch results to *equal* isolated results, which is
  true by construction when both call the same function.

## Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| REQ-001 | The system shall provide a `Scenario` model with `trade_events`, `rate_shocks`, `demand_shocks`, and `metadata`, and a `TradeEvent` model supporting all seven §13.1 types (`BUY`, `SELL`, `TRANSFER_IN`, `TRANSFER_OUT`, `NEW_LOAN`, `RETURN`, `RECALL`) with `effective_date`-gated timing. | must |
| REQ-002 | `apply_scenario` shall apply only trade events with `effective_date <= request.effective_date`, sorted deterministically by `(effective_date, event-type priority, event_id)`, and shall never mutate the baseline `OptimizationRequest` or any of its nested records. | must |
| REQ-003 | `apply_scenario` shall reject a scenario containing more than one effective `RETURN` (or more than one effective `RECALL`) event referencing the same `route_id` — an unordered composition conflict (§13.2) — with a structured error, not a silent pick-one. | must |
| REQ-004 | `apply_scenario` shall reject a scenario whose cumulative `SELL`/`TRANSFER_OUT` effect would drive an inventory record's `total_lendable_shares` negative (physically impossible), with a structured error. | must |
| REQ-005 | `RateShock`/`DemandShock` shall be applied unconditionally (not gated by `effective_date` — they represent scenario-level market assumptions, not dated real-world events) by overriding the named route's `fee_rate` or the named demand forecast's fields before re-compilation. | must |
| REQ-006 | The system shall re-run `validation.raise_if_invalid` on the scenario-modified request before solving it (§13.3 step 8), surfacing any newly-introduced inconsistency as a normal `InputValidationError` rather than a confusing downstream failure. | must |
| REQ-007 | `run_scenario` shall produce a `ScenarioComparison` containing: normalized status/feasibility, objective and economics-component deltas, per-inventory balance deltas, per-route allocation deltas, `TRADE_REDUCED_SUPPLY`-tagged routes with an estimated per-route revenue delta, and warnings (including an explicit warning whenever a scenario-modified inventory's recomputed `available_to_lend_shares` goes negative — an oversold-pending-recall state). | must |
| REQ-008 | `run_scenarios` shall produce results identical (modulo `run_id`/`created_at`/`solver.runtime_seconds`, the same three fields T12 already excludes) to calling `run_scenario` once per scenario in the same order. | must |
| REQ-009 | The system shall define `services.ScenarioService` as a `runtime_checkable` `Protocol` (`run(baseline, scenarios) -> tuple[ScenarioComparison, ...]`) and provide a concrete implementation composing `InventoryOptimizer`, `apply_scenario`, and `run_scenarios`. | must |
| REQ-010 | The CLI's `scenarios` subcommand shall accept a JSON file containing either one `Scenario` or a JSON array of `Scenario` objects, run it/them against a request loaded the same way `optimize` does, and write the resulting comparison(s) as JSON to `--output`/stdout with an exit code distinguishing all-feasible, some-infeasible, and invalid-input outcomes. | must |
| REQ-011 | The system shall provide `run_stress_test(baseline_result, baseline_request, scenarios, optimizer) -> StressTestReport` summarizing a batch of scenario comparisons: per-scenario one-line verdict, counts of feasible/infeasible/verification-failed scenarios, and the single worst-case scenario by objective delta among the feasible ones. | should |

## Non-Functional Requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | Baseline immutability (`SCN-001`) | `apply_scenario`/`run_scenario`/`run_scenarios` never call a mutating method on the input `OptimizationRequest`; `baseline.model_dump_json()` is byte-identical before and after any of them run. |
| NFR-002 | Batch/isolated equivalence (`SCN-003`) | See REQ-008 — this is the same property, stated as a target rather than a one-time requirement. |
| NFR-003 | No spurious re-validation failures | A scenario-modified `OptimizationRequest` is never round-tripped through `model_validate`/`model_dump_json`-then-reload before being handed to `InventoryOptimizer.optimize()` — only `.model_copy()`, which does not re-run each nested record's own construction-time validators (see `plan.md`'s design note). |

## Acceptance Criteria

| ID | Given / When / Then | Covers |
| --- | --- | --- |
| AC-001 | Given the E2 fixture (a single route/demand-group, fee 2.00%, `epsilon=0.5`) and a `RateShock` raising the route's fee to 3.00%, when `run_scenario` executes, then the scenario's effective demand cap is `65.3197264742` (±1e-6), matching `EXAMPLES.md`'s E2 table, and its allocation carries `ELASTICITY_REDUCED_DEMAND`. | REQ-001, REQ-005 |
| AC-002 | Given AC-001's scenario, when the baseline request is inspected after `run_scenario` returns, then `baseline.model_dump_json()` is unchanged from before the call. | REQ-002, NFR-001 |
| AC-003 | Given the E3 "feasible open-loan variant" fixture (100 lendable, current book 80/20, zero transition costs, no utilization cap) and a `SELL` of 30 shares effective on the request's `effective_date`, when `run_scenario` executes, then the scenario result shows Route A at 70, Route B at 0, and the comparison tags both routes `TRADE_REDUCED_SUPPLY` with the correct allocation deltas (-10, -20). | REQ-001, REQ-002, REQ-007 |
| AC-004 | Given the E3 "infeasible term/notice variant" fixture (Route A's `hard_minimum_quantity_shares=80` through the sale date), when `run_scenario` executes, then the comparison's status is `INFEASIBLE` and no allocation recommendation is produced. | REQ-001, REQ-002, REQ-007 |
| AC-005 | Given a scenario with two `RETURN` events referencing the same `route_id`, when `apply_scenario` executes, then it raises a structured error rather than silently applying one and discarding the other. | REQ-003 |
| AC-006 | Given a scenario with a `SELL` larger than an inventory record's `total_lendable_shares`, when `apply_scenario` executes, then it raises a structured error rather than producing a negative `total_lendable_shares`. | REQ-004 |
| AC-007 | Given three scenarios run via `run_scenarios` and the same three scenarios run one at a time via `run_scenario`, when both sets of results are compared field-by-field (excluding `run_id`/`created_at`/`solver.runtime_seconds` in each nested `OptimizationResult`), then they are identical. | REQ-008, NFR-002 |
| AC-008 | Given an `InventoryOptimizer` instance, when checked with `isinstance(impl, ScenarioService)`, then it evaluates `True` without explicit subclassing (mirroring T12's own `OptimizationService` check). | REQ-009 |
| AC-009 | Given a JSON file with a single `Scenario` and one with a JSON array of two `Scenario`s, when `inventory-optimizer scenarios --request ... --scenario <file>` runs against each, then the single-scenario file produces one comparison object and the array file produces a JSON array of two, both with an exit code distinguishing all-feasible from any-infeasible. | REQ-010 |
| AC-010 | Given five scenarios where two are engineered to be infeasible, when `run_stress_test` executes, then its report counts `infeasible == 2`, `feasible == 3`, and names the worst-case scenario among the three feasible ones by objective delta. | REQ-011 |

## Data & Dependencies

- `domain.requests.OptimizationRequest`, `domain.inventory.SecurityInventory`,
  `domain.loans.LoanRoute`, `domain.demand.DemandForecast` — read (via `.model_copy()`) and never
  mutated.
- `validation.raise_if_invalid` (already implemented) — re-validation step.
- `facade.InventoryOptimizer` (T12) — the composed five-stage pipeline each scenario re-runs.
- `reporting.explanations`, `components.objective_terms.fee_revenue.fee_revenue_coefficient` —
  reused, not re-implemented, for `ELASTICITY_REDUCED_DEMAND` (automatic, no code change) and the
  per-route revenue-delta estimate for `TRADE_REDUCED_SUPPLY`-tagged routes respectively.
- `specs/engine_spec/EXAMPLES.md` E2, E3 — golden fixtures for AC-001 through AC-004.
- `specs/engine_spec/TRACEABILITY.md`'s `SCN-001`, `SCN-002`, `SCN-003` rows — this spec's evidence
  target. `SCN-004` stays `SPECIFIED` (tagged `T40`, agency/prime desk events, out of scope here).

## Risks

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| RISK-001 | A `SELL`/`RECALL` that drives a scenario-modified inventory's recomputed `available_to_lend_shares` negative (oversold, pending recall) is a real, valid state this spec deliberately allows (see `plan.md`), but could otherwise mask a genuine upstream data bug if it passed silently. | A desk user cannot tell "this is a deliberate stress" from "the input data was wrong." | REQ-007 requires an explicit warning on every such occurrence, surfaced in `ScenarioComparison.warnings`, not hidden. |
| RISK-002 | Conflicting `RETURN`/`RECALL` composition on the same route, if not rejected, would silently depend on Python dict/sort iteration order rather than an explicit rule. | Two analysts building "the same" scenario in a different event order get different, unexplained results. | REQ-003's explicit rejection (AC-005) turns a silent footgun into a caught, actionable error. |
| RISK-003 | `run_scenario`'s per-route "lost revenue" estimate for `TRADE_REDUCED_SUPPLY` routes reuses only `fee_revenue_coefficient` (the one objective component with a public, reusable coefficient function) — a route whose economics are dominated by (future) `transition_cost` or other components would have an incomplete estimate. | A desk user could read the per-route delta as complete P&L when it is fee-revenue only. | `ScenarioComparison`'s field is explicitly named/documented as a fee-revenue-only estimate, not "P&L"; `plan.md`'s Non-Goals restate the limit inherited from T11 (`EconomicsSummary` is per-component, not per-route). |

## Assumptions & Open Questions

- Assumption: event-type sort priority (§13.3's "type priority" tie-break, no concrete ordering
  given anywhere in `01_SPEC.md`) uses §13.1's own listed order (`BUY`, `SELL`, `TRANSFER_IN`,
  `TRANSFER_OUT`, `NEW_LOAN`, `RETURN`, `RECALL`) as a simple, deterministic, documented choice.
- Assumption: `NEW_LOAN` (§13.1: "adds or changes a candidate route/demand cap, not supply") means
  marking an existing, already-present-but-currently-ineligible `LoanRoute` as `eligible=True`
  (optionally raising `maximum_quantity_shares` if the event carries an override) — not fabricating
  a wholly new route inline, since the request's route list is fixed at request-construction time
  and `01_SPEC.md` says the event "requires a candidate route" (implying reference, not creation).
- Assumption: `RETURN` reduces `route.current_quantity_shares` by `min(event.quantity_shares,
  current)`; `RECALL` lowers `route.maximum_quantity_shares` (floored at
  `hard_minimum_quantity_shares`) and, if the new maximum is now below `current_quantity_shares`,
  forces the same reduction `RETURN` would. Both correspondingly adjust the owning inventory
  record's `on_loan_shares` (and `available_to_lend_shares`) by the same amount, since these two
  event types (unlike `BUY`/`SELL`/`TRANSFER_*`) change a specific route's booked quantity, and
  `validation.reconciliation.check_on_loan_reconciliation` (already implemented, always re-run per
  REQ-006) requires `sum(route.current_quantity_shares) == inventory.on_loan_shares` to keep
  holding after they run.
- Open question: whether `run_stress_test`'s "worst case" should rank by objective delta alone or
  by a weighted combination (objective delta, unfilled-demand delta, utilization delta). `plan.md`
  picks objective delta alone as the simplest defensible default for a "basic" capability; revisit
  once a real stress-testing workflow has an opinion.

## Exceptions

None recorded.
