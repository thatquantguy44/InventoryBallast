# Spec: Multi-period settlement — deterministic projection and joint LP (Phase 5 item 2)

- **ID:** 0010-multi-period-settlement
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code)
- **Approver:** Joshua Lutkemuller, CFA (2026-09-07 — resolved all three blocking design questions:
  build both the deterministic projection *and* the full joint multi-period LP, sequenced (the
  projection first, as a smaller, self-contained, also-independently-useful deliverable, then the
  joint LP building on the same event-timing primitives); validate a known future `RECALL` event's
  timing against `LoanRoute.recall_notice_days` in V1 rather than deferring it; the per-day
  discount rate is a configurable field (`MultiPeriodConfig.daily_discount_rate`), defaulting to
  zero for now.)
- **Last updated:** 2026-09-07

> WHAT and WHY only. No implementation detail — that belongs in `plan.md`.

## Problem & Context

Today the engine solves exactly one snapshot: every `OptimizationRequest` is evaluated at a single
`effective_date`, and `FormulationConfig.planning_horizon_days` is only a day-count scalar feeding
`fee_revenue`'s day-count fraction — not a time-indexed decision sequence. A sale booked today, a
recall notice, a borrower return, and their eventual settlement several days later cannot be
represented; the desk question "if I lend this today, and the sale/recall I already know about
actually settles on its scheduled date, what does my book look like three days from now — and
would I actually decide differently today if the model considered that future?" can only be
answered by manually re-running whole new snapshots by hand.

`01_SPEC.md` §22.11 already specifies the natural extension, normatively, with time buckets `t in
T` and recursive balance identities:

```text
on_loan_i,t    = on_loan_i,t-1 + new_loans_i,t - returns_i,t - recalls_i,t
available_i,t  = lendable_i,t - on_loan_i,t - reserved_i,t - committed_i,t
lendable_i,t   = lendable_i,t-1 + settled_buys_i,t - settled_sells_i,t
                 + transfers_in_i,t - transfers_out_i,t + corporate_action_delta_i,t
```

and says the resulting deterministic model "should precede a fully stochastic formulation because
it captures most operational realism while remaining explainable" (§22.11) — §22.12's
scenario-tree/stochastic extension is a later step, not this one. `00_PLAN.md`'s own "Deferred
extensions" list names "Multi-period stochastic optimization" as explicitly out of V0 scope, but
does not exclude this deterministic precursor.

**§13.2 already anticipates exactly this.** The existing `TradeEvent` domain model (Section 13.1;
`domain/scenarios.py`) already carries `trade_date`/`effective_date`/`settlement_date` fields for
all seven event kinds, and §13.2 states: "Only events effective by the request `effective_date`
alter V0 supply or route state. Later events are retained in scenario metadata but do not affect a
single-period solve." Multi-period settlement is what finally reads the events a single-period
solve deliberately ignores.

**This spec builds two designs, in sequence, both satisfying §22.11's balance identities:**

1. **The deterministic projection** — period 0 stays exactly today's existing single-period
   LP/MIP/QP solve, the only period actually *decided*. Periods 1..N are a mechanical,
   unoptimized projection of what already-known future events will do to the already-solved book,
   reusing `scenarios.apply.apply_scenario`'s existing per-event-type mechanics. Smaller, and
   independently useful even before the joint LP exists (a desk can already answer "what happens to
   my book" without needing "what should I have done differently").
2. **The joint multi-period LP** — the same §22.11 identities compiled as real constraints across
   every period, with route-quantity decision variables at every period and the objective jointly
   maximizing discounted revenue across the whole horizon, so period-0 allocation can genuinely
   account for a known future event rather than merely being reported against it afterward. Reuses
   the projection's own event-timing/ordering primitives (`select_effective_events`) and every
   existing baseline LP component, replicated per period.

Both designs share one new recall-notice validation: a known future `RECALL` must respect
`LoanRoute.recall_notice_days` — an operationally impossible recall (notice shorter than the
route's own contractual minimum) is rejected, not silently honored.

## Goals

- Two new, optional `OptimizationRequest` fields — `planning_periods` (ordered future dates) and
  `known_future_events` (reusing the existing `TradeEvent` type unchanged) — both empty by default,
  shared by both designs, so an ordinary request is completely unaffected.
- Validate a known future `RECALL` event's `(effective_date - trade_date)` against
  `route.recall_notice_days`, rejecting (structured issue) an operationally impossible recall,
  applied uniformly regardless of which design consumes the events.
- **Design B (deterministic projection):** a new, additive `settlement/` package projecting the
  already-solved period-0 book forward through each planning period, reusing
  `scenarios.apply.apply_scenario`'s existing, unchanged per-event-type mechanics, producing
  §22.11's balance identities per inventory per period plus discounted per-period economics
  (reusing `fee_revenue_coefficient` unchanged), in a new, separate, additive result type
  (`domain/settlement.py::MultiPeriodProjection`) — mirroring how `ScenarioComparison`/
  `StressTestReport` are already distinct result types.
- **Design A (joint multi-period LP):** a new compiler (`formulation/multi_period.py`) extending
  every existing baseline LP component (unchanged for period 0; the identical structure,
  period-parameterized, for periods 1..N) with time-indexed route-quantity/transition variables
  per §22.11, auto-routed exactly like every other capability-gated extension (MIP, QP, discrete
  fee tiers) — strictly opt-in, byte-identical single-period behavior when `planning_periods` is
  empty.
- One consistent result shape for both designs (`MultiPeriodProjection`, with a `mode` field
  distinguishing "projected" from "jointly optimized" periods), so a desk reads one report
  regardless of which design produced it.
- A configurable per-day discount rate (`MultiPeriodConfig.daily_discount_rate`, default `0.0`)
  applied consistently by both designs.
- Unconditional, prominent disclosure of which periods were actually *decided* versus merely
  *projected*, per solve — never blurred, regardless of which design ran.

## Non-Goals

- **§22.12's stochastic/scenario-tree extension** (probability-weighted scenarios, CVaR, chance
  constraints) — untouched; `00_PLAN.md`'s own "Deferred extensions" list already excludes this,
  and §22.11 itself says the deterministic form should come first.
- **Real business-day/holiday calendar resolution** — every date in `planning_periods` is treated
  as a valid settlement day for V1. No calendar port or adapter exists anywhere in this repo today;
  inventing one is out of scope here.
- **Corporate-action deltas and cross-currency/FX effects on lendable quantity** (§22.11's own
  `corporate_action_delta_i,t` term) — fixed at zero for V1; no corporate-action domain model
  exists yet.
- **Time-varying demand forecasts, fee rates, or prices across the horizon** — the joint LP holds
  each demand group's elasticity-evaluated cap, and each route's fee/price/cost coefficients,
  constant across every period; only quantity and per-period discounting vary. A future spec can
  extend `known_future_events` (or a new event type) to carry period-specific re-pricing; this one
  does not.
- **MIP or QP triggers combined with a multi-period request** — the joint LP's V1 is a pure
  continuous LP across periods. A request that is both multi-period *and* would otherwise need
  `compile_mip`/`compile_qp` (all-or-none, lot sizes, cardinality, discrete fee tiers, the
  allocation-stability penalty) fails closed, mirroring exactly how a MIP-triggering request
  combined with a configured QP penalty already fails closed today (`MIQP_UNSUPPORTED`). Combining
  discrete business rules with joint multi-period optimization is a real, separately-scoped
  follow-up, not attempted here.
- **A CLI subcommand** — library function only for V1, mirroring how `run_stress_test`
  (`specs/0004-scenario-engine/`) shipped the same way before any desk need for a CLI surface
  existed.
- **Changing what `Scenario`/`apply_scenario` mean for today's single-period what-if
  comparisons** — `known_future_events` is a new field directly on `OptimizationRequest` (the
  baseline's own already-known commitments), never routed through `Scenario`/`ScenarioComparison`.

## Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| REQ-001 | The system shall add `OptimizationRequest.planning_periods: tuple[date, ...]` (strictly increasing, every date later than `effective_date`) and `OptimizationRequest.known_future_events: tuple[TradeEvent, ...]` (the existing, unchanged `TradeEvent` type), both empty by default, shared by both designs. | must |
| REQ-002 | The system shall reject (structured issue) any request supplying `known_future_events` while `planning_periods` is empty. | must |
| REQ-003 | The system shall reject (structured issue) any `known_future_events` `RECALL` entry whose `(effective_date - trade_date).days` is less than the referenced route's `recall_notice_days`, applied uniformly for both designs. | must |
| REQ-004 | **(Design B)** For each planning period, the system shall compute the projected request state by applying, in the existing Section 13.3 deterministic order, every `known_future_events` entry effective in that period, reusing the existing, unchanged per-event-type mechanics `scenarios.apply.apply_scenario` already implements. | must |
| REQ-005 | **(Design B)** The projection's period-0 starting state shall be the already-solved allocation (each route's solved post-quantity as its `current_quantity_shares`). | must |
| REQ-006 | **(Design B)** The system shall report, per inventory record and period, the projected `total_lendable_shares`/`on_loan_shares`/`available_to_lend_shares`/utilization, matching Section 22.11's identities exactly. | must |
| REQ-007 | **(Design B/A, shared)** The system shall report, per period, net lending economics (fee revenue via the existing `fee_revenue_coefficient` formula, generalized to that period's own day-count length) at the configurable per-day discount rate, plus the horizon total. | must |
| REQ-008 | **(Design B/A, shared)** The system shall introduce one additive result type (`domain/settlement.py::MultiPeriodProjection`, with `PeriodBalance`/`PeriodEconomics` records and a `mode` field: `"projected"` or `"jointly_optimized"`) rather than a change to `OptimizationResult`. | must |
| REQ-009 | **(Design A)** The system shall introduce a new multi-period LP compiler (`formulation/multi_period.py`) with one route-quantity/transition-variable set per planning period (period 0 through N), compiling §22.11's balance identities as real per-period constraints, reusing every existing baseline LP component's exact mathematical structure (unchanged for period 0; period-parameterized, not re-derived, for periods 1..N). | must |
| REQ-010 | **(Design A)** Known future events shall enter the joint LP as exogenous per-period bound/parameter adjustments (reusing REQ-003's timing/ordering rules), never as new decision variables. | must |
| REQ-011 | **(Design A)** The objective shall jointly maximize discounted net revenue across every period, letting period-0 allocation account for a known future event rather than merely being reported against it afterward. | must |
| REQ-012 | **(Design A)** A request with empty `planning_periods` shall compile via the existing `compile_lp`/`compile_mip`/`compile_qp` unchanged (byte-identical); a request combining `planning_periods` with any MIP/QP trigger shall fail closed with a structured issue rather than silently dropping one or the other. | must |
| REQ-013 | The system shall provide golden tests reproducing, by hand, fixtures for both designs: a known future `RECALL`/`BUY` projected across two periods (Design B), and a small joint-LP fixture where period-0's allocation genuinely differs from the single-period optimum because of a known future event (Design A) — proving the joint LP is not merely the projection in disguise. | must |

## Non-Functional Requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | No behavior change for a request with empty `planning_periods` | Every existing test (239, pre-this-spec) continues to pass unchanged; `facade.optimize()`'s compiled output is byte-identical for both `compile_lp`/`compile_mip`/`compile_qp`, since no compiler reads the new fields unless they are set. |
| NFR-002 | Deterministic and reproducible | No wall-clock, no random state; every `planning_periods` date is treated as a valid settlement day, stated as an explicit simplification. |
| NFR-003 | Honest disclosure | `MultiPeriodProjection.mode` is unconditional and set only by the two sanctioned constructors (`settlement.project.project_multi_period`, `formulation.multi_period`'s own result builder); nothing implies a projected period was optimized, or vice versa. |
| NFR-004 | No silent clipping | A projection step that would violate `scenarios.apply`'s own existing invariants reuses its existing `ScenarioApplicationError`/warning behavior; the joint LP's own infeasibility is reported through the existing solver-status/verification machinery, never silently relaxed. |
| NFR-005 | Global optimality preserved for the joint LP | Because it stays a continuous LP (REQ-012's MIP/QP exclusion), the existing HiGHS LP status normalization applies unchanged — proven-optimal is proven-optimal, exactly as today. |

## Acceptance Criteria

| ID | Given / When / Then | Covers |
| --- | --- | --- |
| AC-001 | Given a request with empty `planning_periods`, when solved via `optimize()`, then the result is byte-identical to today's, for LP, MIP, and QP requests alike. | NFR-001 |
| AC-002 | Given `known_future_events` set with `planning_periods` empty, when constructing the request, then construction raises a validation error. | REQ-002 |
| AC-003 | Given a known future `RECALL` whose notice is shorter than the route's `recall_notice_days`, when the request is validated, then it is rejected with a structured issue. | REQ-003 |
| AC-004 | Given a two-period fixture with a known future `RECALL` in period 2, when projected (Design B), then period 1's balances equal the solved period-0 state exactly, and period 2's on-loan/available shares reflect the recall, matching a hand computation. | REQ-004, REQ-005, REQ-006 |
| AC-005 | Given the same fixture, when projected, then period 2's discounted fee revenue equals a hand-computed value. | REQ-007 |
| AC-006 | Given a joint-LP fixture where a known future `RECALL` makes it worth lending less at period 0 than the single-period-optimal quantity, when solved via the joint LP, then period 0's allocation is strictly less than the single-period optimum and the horizon's total discounted objective exceeds what period-0-only optimization plus the recall would have produced. | REQ-009, REQ-010, REQ-011 |
| AC-007 | Given a joint-LP request combined with an `all_or_none` route or a configured QP penalty, when compiled, then it fails closed with a structured issue naming the conflict. | REQ-012 |
| AC-008 | Given any `MultiPeriodProjection` from either design, when inspected, then `mode` is set correctly and unconditionally. | REQ-008, NFR-003 |

## Data & Dependencies

- `domain.scenarios.TradeEvent` — reused unchanged as the shape of `known_future_events`.
- `scenarios.apply.apply_scenario` (T13-T14) — its per-event-type mechanics and timing/ordering
  rules are extracted into shared, reusable helpers (`select_effective_events`/`apply_events`),
  used by both Design B and Design A; `apply_scenario`'s own existing tests must keep passing
  unchanged as the acceptance bar for that refactor.
- `formulation.lp.REQUIRED_CONSTRAINTS`/`REQUIRED_OBJECTIVES` and every component they name — their
  exact mathematical structure is replicated per period by Design A, not re-derived.
- `components.objective_terms.fee_revenue.fee_revenue_coefficient` (T08) — generalized to accept a
  period-specific day-count fraction rather than only `config.formulation.planning_horizon_days`.
- `formulation.compiler_support` — gains a `needs_multi_period`/`multi_period_required_issues`
  predicate pair, mirroring `needs_mip`/`needs_qp`, and the MIP/QP-conflict fail-closed rule (REQ-012).
- `domain.requests.OptimizationRequest` — gains the two optional fields (REQ-001).
- `domain.results.OptimizationResult` — untouched (REQ-008's result type is separate).
- New config: `config.models.MultiPeriodConfig.daily_discount_rate`, defaulting to `0.0`.
- `specs/spec002/TRACEABILITY.md` — no existing row covers §22.11/§22.12; `plan.md`/`tasks.md`
  propose new `MPS-*` rows.

## Risks

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| RISK-001 | A `MultiPeriodProjection` could be misread if `mode` is not checked — a desk user glancing at per-period numbers without noticing whether they were solved or projected. | Acting on a projected trajectory as though it were the jointly-optimized plan, or vice versa. | REQ-008's `mode` field, unconditionally set by exactly two sanctioned constructors; `AC-008` pins this. |
| RISK-002 | Reusing `TradeEvent` (designed for `Scenario`'s hypothetical what-if comparisons) as "already-known, committed future fact" input blurs a semantic line `specs/0004-scenario-engine/plan.md` already flagged once. | Confusing "what we're testing" with "what we already know will happen." | `known_future_events` is a new field directly on `OptimizationRequest`, never routed through `Scenario`/`apply_scenario`'s own comparison path. |
| RISK-003 | `apply_scenario`'s internals were built and tested for a single cutoff date; repurposing them for a rolling per-period cutoff (Design B) and for exogenous per-period bound construction (Design A, a related but not identical reuse) must stay genuinely behavior-preserving for the existing single-period caller. | A careless refactor could silently change today's scenario-engine behavior. | `plan.md`'s Approach requires the refactor to keep `apply_scenario`'s own existing tests passing unchanged, before any new code is layered on top; Design A's own bound-construction logic is recorded as related-but-distinct reuse, not claimed as identical, in `plan.md`. |
| RISK-004 | The joint LP (Design A) multiplies variable/row count by route count × period count — the same `J*K`-shaped growth `specs/0009-discrete-fee-tier-pricing/spec.md` RISK-001 flagged for its own tier dimension, here potentially larger since it applies to every route, not just tiered-group routes. | A desk with a long horizon and many routes could see materially slower solves. | `planning_periods` is strictly opt-in and empty by default (NFR-001); a `slow`-marked scale test (tasks.md) establishes the shape of the growth, following `specs/0005-test-hardening/`'s benchmark precedent. |
| RISK-005 | Building both designs in one spec is a larger, slower-to-review change than either alone. | Longer time-to-first-value; more surface area for a defect to hide in before review. | Sequenced delivery (Design B first, fully tested and usable standalone, before Design A begins) rather than one large undifferentiated change — `tasks.md` orders the work this way explicitly. |

## Assumptions & Open Questions

- Assumption: `known_future_events` belongs on `OptimizationRequest` itself (the baseline's own
  known commitments), not on `Scenario` — see RISK-002.
- Assumption: every date in `planning_periods` is a valid settlement day for V1 (no calendar).
- Assumption: demand caps, fee rates, and prices are constant across the horizon for V1 (Non-Goals)
  — only quantity and discounting vary by period.
- Resolved (2026-09-07, owner): build both designs, sequenced; validate recall-notice timing in V1;
  the discount rate is configurable, defaulting to zero. See the Approver line above.
- Open question: should a future spec extend `known_future_events` (or a new event type) to carry
  period-specific re-pricing, once a real desk need for time-varying fees within the horizon
  exists? Deferred until that need is concrete.
- Open question: once MIP/QP business rules are wanted *within* a multi-period request (REQ-012's
  current exclusion), does that need a genuinely new mixed-integer multi-period compiler, or can
  the existing MIP/QP compilers be parameterized the same way Design A parameterizes the baseline
  LP? Deferred — no desk need identified yet.

## Exceptions

None recorded.
