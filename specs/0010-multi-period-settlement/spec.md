# Spec: Deterministic multi-period settlement (Phase 5 item 2, deterministic form)

- **ID:** 0010-multi-period-settlement
- **Status:** Draft
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code)
- **Approver:** _pending — three open design questions below need owner sign-off before this can move to Approved_
- **Last updated:** 2026-09-07

> WHAT and WHY only. No implementation detail — that belongs in `plan.md`.

## Problem & Context

Today the engine solves exactly one snapshot: every `OptimizationRequest` is evaluated at a single
`effective_date`, and `FormulationConfig.planning_horizon_days` is only a day-count scalar feeding
`fee_revenue`'s day-count fraction — not a time-indexed decision sequence. A sale booked today, a
recall notice, a borrower return, and their eventual settlement several days later cannot be
represented; the desk question "if I lend this today, and the sale/recall I already know about
actually settles on its scheduled date, what does my book look like three days from now — and is
today's allocation quietly infeasible against that known future?" can only be answered by manually
re-running a whole new snapshot at each future date by hand.

`01_SPEC.md` §22.11 already specifies the natural extension, normatively, with time buckets `t in
T` and recursive balance identities:

```text
on_loan_i,t    = on_loan_i,t-1 + new_loans_i,t - returns_i,t - recalls_i,t
available_i,t  = lendable_i,t - on_loan_i,t - reserved_i,t - committed_i,t
lendable_i,t   = lendable_i,t-1 + settled_buys_i,t - settled_sells_i,t
                 + transfers_in_i,t - transfers_out_i,t + corporate_action_delta_i,t
```

and it says the resulting deterministic model "should precede a fully stochastic formulation
because it captures most operational realism while remaining explainable" (§22.11) — i.e. §22.12's
scenario-tree/stochastic extension is a *later* step, not this one. `00_PLAN.md`'s own "Deferred
extensions" list names "Multi-period stochastic optimization" as explicitly out of V0 scope, but
does not exclude this deterministic precursor — the same relationship
`specs/0009-discrete-fee-tier-pricing/` already used (V0 deferred "joint continuous optimization of
fee and quantity"; that spec built the discrete alternative instead, not the deferred thing
itself).

**§13.2 already anticipates exactly this.** The existing `TradeEvent` domain model (Section 13.1;
`domain/scenarios.py`) already carries `trade_date`/`effective_date`/`settlement_date` fields for
all seven event kinds, and §13.2 states: "Only events effective by the request `effective_date`
alter V0 supply or route state. Later events are retained in scenario metadata but do not affect a
single-period solve." Multi-period settlement is what finally reads the events a single-period
solve deliberately ignores.

**This spec builds the deterministic *projection* form, not the full joint multi-period LP.** Two
designs both satisfy §22.11's balance identities; they answer different desk questions and one of
them is a materially larger undertaking. This spec recommends, and specifies, the narrower one —
see the Open Questions below for the full trade-off and why it is not decided silently.

## Goals

- Two new, optional `OptimizationRequest` fields — `planning_periods` (ordered future dates) and
  `known_future_events` (reusing the existing `TradeEvent` type unchanged) — both empty by default,
  so an ordinary request is completely unaffected.
- A new, additive `settlement/` package (mirroring `scenarios/`'s own shape) that projects the
  already-solved period-0 book forward through each planning period by reapplying the existing,
  unchanged per-event-type mechanics `scenarios.apply.apply_scenario` already implements for all
  seven `TradeEventType` kinds, producing §22.11's exact balance identities per inventory per
  period.
- Per-period discounted net lending economics, reusing the existing, unchanged
  `fee_revenue_coefficient` formula against each period's own projected quantities.
- A new, separate, additive result type (`domain/settlement.py::MultiPeriodProjection`) — mirroring
  how `ScenarioComparison`/`StressTestReport` are already distinct result types rather than fields
  added to `OptimizationResult` itself.
- Unconditional, prominent disclosure that periods beyond 0 are a mechanical projection of
  already-known future events against the already-solved period-0 allocation — never a
  re-optimized plan — so a desk cannot mistake "the book we project" for "the plan we solved for."
- Formulation-independence: works identically regardless of whether period 0 was solved via LP,
  MIP, or QP, since it operates only on the already-solved result, never on the compiler.

## Non-Goals

- **The full joint multi-period LP** (time-indexed decision variables across every route and
  period, with the objective jointly optimized across the whole horizon) — §22.11's literal
  formula sketch, and a materially larger undertaking (route × period variable growth, time-varying
  route bounds, a real calendar). Deferred to a follow-up spec once this projection form is in
  production and a real desk need justifies the larger investment — see Open Questions.
- **§22.12's stochastic/scenario-tree extension** (probability-weighted scenarios, CVaR, chance
  constraints) — untouched; `00_PLAN.md`'s own "Deferred extensions" list already excludes this,
  and §22.11 itself says the deterministic form should come first.
- **Real business-day/holiday calendar resolution** — every date in `planning_periods` is treated
  as a valid settlement day for V1. No calendar port or adapter exists anywhere in this repo today;
  inventing one is out of scope here.
- **Corporate-action deltas and cross-currency/FX effects on lendable quantity** (§22.11's own
  `corporate_action_delta_i,t` term) — fixed at zero for V1; no corporate-action domain model
  exists yet, and this spec does not invent one.
- **Validating a `RECALL` event's timing against `LoanRoute.recall_notice_days`** — the projection
  applies whatever date the event already carries, honestly, without a new notice-sufficiency
  check. A plausible, separately-scoped follow-up — see Open Questions.
- **Lot/election-driven MIP interaction within the projected horizon** (§22.11: "lots/elections
  make it MIP") — the projection reads a route's already-solved quantity; it introduces no discrete
  variables of its own.
- **A CLI subcommand** — library function only for V1, mirroring how `run_stress_test`
  (`specs/0004-scenario-engine/`) shipped the same way before any desk need for a CLI surface
  existed.
- **Changing what `Scenario`/`apply_scenario` mean for today's single-period what-if
  comparisons** — `known_future_events` is a new field directly on `OptimizationRequest` (the
  baseline's own already-known commitments), never routed through `Scenario`/`ScenarioComparison`,
  so that machinery's "hypothetical what-if" semantics stay exactly as documented today.

## Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| REQ-001 | The system shall add `OptimizationRequest.planning_periods: tuple[date, ...]` (strictly increasing, every date later than `effective_date`) and `OptimizationRequest.known_future_events: tuple[TradeEvent, ...]` (the existing, unchanged `TradeEvent` type), both empty by default. | must |
| REQ-002 | The system shall reject (structured issue) any request supplying `known_future_events` while `planning_periods` is empty, since such events could never be applied. | must |
| REQ-003 | For each planning period, the system shall compute the projected request state by applying, in the existing Section 13.3 deterministic order, every `known_future_events` entry whose date falls after the previous period boundary (or `effective_date` for the first period) and on or before this period's boundary — reusing the existing, unchanged per-event-type mechanics `scenarios.apply.apply_scenario` already implements. | must |
| REQ-004 | The projection's period-0 starting state shall be the already-solved allocation (each route's solved post-quantity as its `current_quantity_shares`), not the original pre-solve request. | must |
| REQ-005 | The system shall report, per inventory record and period, the projected `total_lendable_shares`, `on_loan_shares`, `available_to_lend_shares`, and utilization, matching Section 22.11's balance identities exactly. | must |
| REQ-006 | The system shall report, per period, projected net lending economics (fee revenue via the existing, unchanged `fee_revenue_coefficient`, valued at that period's own quantities and day-count fraction) at a configurable per-day discount rate, plus the horizon total. | must |
| REQ-007 | The system shall introduce a new, additive result type (`domain/settlement.py::MultiPeriodProjection`, with `PeriodBalance`/`PeriodEconomics` records) produced by a new `settlement.project.project_multi_period` function, not a change to `OptimizationResult`. | must |
| REQ-008 | The projection shall not alter `formulation`, `facade.InventoryOptimizer.optimize()`, or any compiler — a pure post-solve function callable regardless of which formulation solved period 0. | must |
| REQ-009 | `MultiPeriodProjection` shall unconditionally, prominently record that periods beyond 0 are a mechanical projection against already-known future events, not a re-optimized plan. | must |
| REQ-010 | The system shall provide golden tests reproducing, by hand, a fixture with one known future `RECALL` and one known future `BUY` across two planning periods, and unit tests for REQ-003's boundary/ordering/reuse behavior. | must |

## Non-Functional Requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | No behavior change for a request with empty `planning_periods` | Every existing test (239, pre-this-spec) continues to pass unchanged; `facade.optimize()`'s compiled output is byte-identical, since no compiler/component ever reads the new fields. |
| NFR-002 | Deterministic and reproducible | No wall-clock, no random state; every `planning_periods` date is treated as a valid settlement day (the calendar Non-Goal), stated as an explicit simplification, not an implicit assumption. |
| NFR-003 | Honest disclosure | REQ-009's labeling is unconditional and cannot be suppressed; nothing about `MultiPeriodProjection`'s naming or fields implies periods 1..T were optimized. |
| NFR-004 | No silent clipping | A projection step that would violate `scenarios.apply`'s own existing invariants (e.g. a sell exceeding remaining lendable shares) reuses its existing `ScenarioApplicationError`/warning behavior rather than a second, inconsistent error path. |

## Acceptance Criteria

| ID | Given / When / Then | Covers |
| --- | --- | --- |
| AC-001 | Given a request with empty `planning_periods`, when solved via `optimize()`, then the result is byte-identical to today's. | NFR-001 |
| AC-002 | Given `known_future_events` set with `planning_periods` empty, when constructing the request, then construction raises a validation error. | REQ-002 |
| AC-003 | Given a two-period fixture with a known future `RECALL` reducing a route's quantity in period 2, when projected, then period 1's balances equal the solved period-0 state exactly, and period 2's on-loan/available shares reflect the recall's forced reduction, matching a hand computation. | REQ-003, REQ-004, REQ-005 |
| AC-004 | Given the same fixture, when projected, then period 2's discounted fee revenue equals a hand-computed value using the existing `fee_revenue_coefficient` formula, discounted by the configured rate. | REQ-006 |
| AC-005 | Given a fixture whose known future event would, if applied naively, drive an inventory's lendable shares negative, when projected, then the existing `ScenarioApplicationError` is raised, not silently clipped. | NFR-004 |
| AC-006 | Given a request solved via `compile_mip` or `compile_qp`, when projected, then the projection succeeds identically, proving formulation-independence. | REQ-008 |
| AC-007 | Given any `MultiPeriodProjection`, when inspected, then it carries REQ-009's disclosure labeling unconditionally. | REQ-009, NFR-003 |

## Data & Dependencies

- `domain.scenarios.TradeEvent` — reused unchanged as the shape of `known_future_events`; no new
  event-type system.
- `scenarios.apply.apply_scenario` (T13-T14) — its per-event-type mechanics are reused, refactored
  (per `plan.md`) to accept a rolling cutoff date rather than only `baseline.effective_date`; its
  own existing tests must keep passing unchanged as the acceptance bar for that refactor.
- `components.objective_terms.fee_revenue.fee_revenue_coefficient` (T08) — reused unchanged for
  per-period economics.
- `domain.requests.OptimizationRequest` — gains the two optional fields (REQ-001); every other
  field unchanged.
- `domain.results.OptimizationResult` — untouched (REQ-007's result type is separate, mirroring
  `domain.scenario_results.ScenarioComparison`/`StressTestReport`).
- New config: a per-day discount rate, defaulting to zero (no discounting) so existing configs
  behave identically — see `plan.md`.
- `specs/spec002/TRACEABILITY.md` — this spec has no existing row; `plan.md`/`tasks.md` propose
  new IDs (see Open Questions) since §22.11/§22.12 were never previously tracked.

## Risks

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| RISK-001 | A projection could be mistaken for a true multi-period *optimization* — a desk user might assume the model already found the best multi-day allocation, when period 0 is the only period actually decided. | A desk could act on a projected trajectory believing it was jointly optimized, when it is a mechanical forward-fill of already-known events. | REQ-009's unconditional labeling; this spec's own Non-Goals; the result type and its fields are never named in a way that implies "solved" or "optimal" for periods 1..T. |
| RISK-002 | Reusing `TradeEvent` (designed for `Scenario`'s hypothetical what-if comparisons) as "already-known, committed future fact" input blurs a semantic line `specs/0004-scenario-engine/plan.md` already flagged once (a `SELL` can legitimately represent an "oversold, pending recall" book state). | Confusing "what we're testing" with "what we already know will happen" could misattribute a projected shortfall to the wrong cause. | `known_future_events` is a new field directly on `OptimizationRequest`, never routed through `Scenario`/`apply_scenario`'s own comparison path — see Assumptions. |
| RISK-003 | Choosing the narrower "projection" design over the fuller "joint multi-period LP" is a real, owner-facing scope decision — a desk expecting the fuller design could be surprised the model never reconsiders period-0 allocation in light of a known future event. | Overstated expectations of what this spec actually decides. | **Explicit open question below**, not a silent choice — `plan.md`'s Trade-offs & Alternatives records both designs and the reasoning, mirroring how `specs/0009-discrete-fee-tier-pricing/` surfaced its own three blocking design questions before implementation began. |
| RISK-004 | `apply_scenario`'s internals were built and tested for a single cutoff date (`baseline.effective_date`); repurposing them for a rolling per-period cutoff must stay genuinely behavior-preserving for the existing single-period caller. | A careless refactor could silently change today's scenario-engine behavior while adding multi-period support. | `plan.md`'s Approach requires the refactor to keep `apply_scenario`'s own existing tests passing unchanged, as its own acceptance bar, before any period-projection code is layered on top. |

## Assumptions & Open Questions

- Assumption: `known_future_events` belongs on `OptimizationRequest` itself (the baseline's own
  known commitments), not on `Scenario` (a hypothetical what-if comparison) — see RISK-002.
- Assumption: every date in `planning_periods` is a valid settlement day for V1 (no calendar); a
  stated simplification, not a hidden one — see Non-Goals.
- **Open question, needs owner sign-off:** is the deterministic forward-projection scope (this
  spec) the right first step, or does the desk need the fuller joint multi-period LP from the
  outset? This spec recommends the projection form (mirroring how discrete pricing preceded
  continuous NLP pricing in `specs/0009-discrete-fee-tier-pricing/`), but the two designs answer
  materially different desk questions, and only the owner can weigh that trade-off.
- **Open question, needs owner sign-off:** should `LoanRoute.recall_notice_days` be validated
  against a known future `RECALL` event's own dates in V1 (rejecting an operationally-impossible
  early recall), or is that deferred? This spec defers it (Non-Goals) but flags it rather than
  silently assuming it away (constitution P8).
- **Open question, needs owner sign-off:** what per-day discount rate should V1 default to — zero
  (no discounting, matching every other zero-default extension in this repo, e.g.
  `ObjectiveConfig.allocation_stability_penalty`), or must a real desk-specific rate be supplied
  before this ships? This spec proposes the zero-default convention.
- Open question: should a future joint multi-period LP (if the first open question above resolves
  toward building it) reuse this spec's `planning_periods`/`known_future_events` fields as its own
  input shape, or does it need a materially different contract? Deferred until that spec exists.

## Exceptions

None recorded.
