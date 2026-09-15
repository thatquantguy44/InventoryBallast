# Spec: Expected economics and entity-hierarchy realism (Realism release R1 — T22-T24)

- **ID:** 0012-expected-economics-realism
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code)
- **Approver:** Joshua Lutkemuller, CFA (2026-09-15 — resolved all four open questions: (1) shadow/compare mode is the default, expected mode an explicit opt-in; (2) T24's piecewise-linear unwind cost is deferred to its own spec; (3) the §22.9 fail-closed rule stands, refined through three sub-decisions recorded below; (4) the R-numbering defect is corrected and documented in `TRACEABILITY.md`.)
- **Last updated:** 2026-09-15

> WHAT and WHY only. No implementation detail — that belongs in `plan.md`.

## Problem & Context

`specs/0011-bloomberg-data-foundation/` built the data foundation (`01_SPEC.md` §25's realism
release R0 = T19-T21): point-in-time contracts, the vendor-agnostic port boundary, a synthetic
adapter, and opt-in status/calendar warnings. It deliberately touched **no objective coefficient**
— §22.15's P0 rows are all "Validation only" / "LP bounds/RHS" / "Data architecture."

This spec is the next slice: **T22-T24, which `01_SPEC.md` §26 says "form R1."** §25 defines it as
"Expected economics: legal-entity aggregation, take-up/survival/repricing hazards, dynamic
reserves, liquidity-aware costs, and event economics," and states the consequence plainly: "R1 is
required before presenting model economics as expected realized revenue rather than contractual
run-rate revenue."

That sentence is the whole point of this spec, and also its central risk. Today every dollar the
optimizer reports is a **contractual run-rate** number: `fee_revenue_coefficient` computes
`P_i * tau * (f_j * s_j - c_j)` and assumes the approved post-state quantity stays on loan for the
entire horizon. §22.5 says that is unrealistic and gives the replacement:

```text
expected_active_fraction_j
  = take_up_probability_j * conditional_expected_days_active_j / planning_horizon_days

expected_fee_revenue_j
  = P_i(j) * q_j * tau * expected_active_fraction_j * (f_j * s_j + r_j * h_j)
```

**Three findings shape this spec's scope.**

**1. This repo has no calibration source — the same structural gap R0 had with entitlements.**
§22.5's coefficients are "independently calibrated" and "remain linear when estimated *before*
solve." §22.13 draws the boundary explicitly: "The optimizer receives only validated predictions
and uncertainty, not an opaque feature dataframe." So the optimizer's job here is to *consume*
estimates carrying their own lineage — never to estimate them. That is the same architectural
position elasticity already holds (§12.1: "Elasticity is preprocessing, not an LP decision") and
the same one R0 took for enrichment. This spec therefore delivers the input contracts, the
objective wiring, the switch, and the disclosure; the estimator itself is upstream and out of
scope.

**2. Turning expected economics on is a named governance gate this repo cannot grant.**
`ROADMAPS.md` §7 defines **G3 — "Expected-economics model promotion," owner group "Quant research +
model risk + business."** `TRACEABILITY.md`'s `DAT-005` row carries that same `G3` tag. This is
exactly the situation `PLT-002` already documents for its own `G2C` gate — the code can be complete
while the release approval sits with people outside this repository. §22.5 anticipates the
mechanism: each coefficient carries "a switch allowing the simpler contractual value for controlled
comparison." So expected economics must ship **off by default**, with switching it on an explicit,
disclosed act rather than a silent upgrade.

**3. Only one piece of T24 needs new formulation machinery; everything else extends what exists.**
Verified against the code:

| Piece | Integration point that already exists | New machinery? |
| --- | --- | --- |
| T22 entity aggregation | `components/constraints/counterparty.py` resolves routes via `context.routes_by_borrower[limit.borrower_id]` — aggregation means resolving a limit's scope over a *set* of borrowers | No — same row, wider scope |
| T23 expected economics | `fee_revenue_coefficient()` is the single choke point for revenue, already extended once by `0010` via an optional `day_count_fraction` kwarg | No — one more optional factor |
| T24 dynamic buffer | `ReserveBufferConstraint` already computes `buffer = max(...)` and applies it as a lower bound on `a_i`; §22.7's `required_buffer_i = max(legal_minimum, pending_settlement_need, demand_uncertainty_quantile, event_recall_buffer, liquidity_horizon_buffer)` is literally the same `max` with more terms | No — more arguments to an existing `max` |
| T24 liquidity **PWL** unwind cost | `recall_or_sale_cost_i(v_i) = PWL_i(v_i; knots)` — segment variables this repo has never built (`0009` explicitly left "§14.3's SOS2/segment machinery ... still unbuilt") | **Yes** |

Because `fee_revenue_coefficient` is shared by `contribute()`, `attribute()`,
`validation.solution_verifier`, and `reporting.explanations`, extending *that one function* keeps
all four in agreement by construction rather than by four parallel edits — the same property that
made `0010`'s per-period day count safe.

This spec takes the three no-new-machinery pieces and **defers T24's PWL unwind cost to its own
spec** (owner decision, 2026-09-15): it is the only piece that needs a convexity argument,
breakpoint disclosure (§14.3), and its own benchmark, and bundling it here would put a formulation
change and an economics change in one review.

## Goals

- Add `EntityRelationship` (the §22.3 point-in-time contract `0011` explicitly deferred) plus an
  `enrichment/entity_hierarchy.py` resolver, reusing `0011`'s `resolve_latest_known` unchanged so
  entity mappings are effective-dated and no-look-ahead by construction.
- Let a `CounterpartyLimit` aggregate across an approved legal entity or ultimate parent
  (§22.9's two summations), while a limit with no entity scope keeps today's exact borrower-only
  behavior.
- Honor §22.9's **fail-closed** rule, scoped to §22.9's own qualifier ("fail closed *for hard
  aggregation*"): an unusable mapping rejects the request only where it actually feeds a
  `hard` entity-scoped limit, never silently aggregating on a guess and never silently omitting
  exposure from a limit.
- Make **internal approval, not vendor confidence, the authority** for hard aggregation (§22.9:
  Bloomberg "can propose the hierarchy, but internal credit/legal owners approve"). Confidence
  screens and is reported; it never authorizes.
- Add an optional per-route `ExpectedEconomics` input carrying §22.5's named coefficients, each
  with model version, calibration date, and uncertainty.
- Apply `expected_active_fraction` and the additive expected cost terms through
  `fee_revenue_coefficient`'s single choke point, so objective, attribution, independent
  verification, and explanations stay consistent automatically.
- Ship a **shadow/compare mode as the default**: report what expected economics *would* say
  alongside a contractual solve, without changing a single allocation — the G3-safe posture, and
  the same "report before you optimize" sequencing `0010` used for projection-before-joint-LP.
- Make optimizing *on* expected economics an explicit config act (the repo-side representation of
  G3 having been granted), disclosed in the result, failing closed if estimates are missing.
- Add an optional per-inventory `DynamicBuffer` input with §22.7's five named components, folded
  into `ReserveBufferConstraint`'s existing `max(...)`, and report which component bound.
- Keep the compiled problem a pure LP throughout (NFR-005).

## Non-Goals

- **T24's piecewise-linear liquidity/unwind cost** (§22.7's `PWL_i(v_i; knots)`). Deferred to its
  own spec by owner decision (2026-09-15) — the only piece needing new formulation machinery, a
  convexity argument, and §14.3's breakpoint disclosure.
- **A "conservative inclusion" escape hatch** for unresolved entity mappings (folding an unmapped
  borrower into a parent's sum instead of failing). Deliberately not built (owner decision,
  2026-09-15). It is undefined for the most common failure — a *missing* mapping has no candidate
  parent to be conservative about — and the capability it offers already exists in cleaner form:
  a desk wanting group exposure tracked advisorily sets `CounterpartyLimit.hard = False` and gets a
  warning, which states plainly that the control is advisory rather than dressing a weakened
  control as a safety feature.
- **Estimating anything.** No hazard model, no take-up model, no calibration routine, no feature
  pipeline. Estimates are inputs with lineage (§22.13). A repo-side estimator would be exactly the
  "opaque feature dataframe" §22.13 forbids.
- **Granting G3.** Nothing here approves expected economics for production use; it builds the
  switch and the evidence surface that a G3 review would examine.
- **§22.6's censoring-aware hierarchical elasticity** (T25) — R2, explicitly downstream.
- **Robust/CVaR scenarios (T26), multi-period balances beyond `0010` (T27), transformation graphs
  (T28)** — R2/R3.
- **Reinvestment income (`r_j * h_j`)** — §22.5's formula includes it, but
  `objective_terms/reinvestment.py` has never been built (§28 defers it) and building it here would
  smuggle a second economic change into an already-large review. The expected-economics factor
  applies to the existing fee-revenue term; reinvestment stays a tracked follow-up.
- **Changing what a contractual solve produces.** With nothing supplied, every number is
  byte-identical to today.

## Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| REQ-001 | The system shall add an `EntityRelationship` contract (entity ID, legal-entity ID, ultimate-parent ID, relationship type, `ownership_confidence`, `approval_reference`, effective interval), carried in `0011`'s existing `PointInTimeValue` envelope. `approval_reference` records an internal credit/legal approval; `ownership_confidence` is the vendor's own score. | must |
| REQ-002 | `enrichment.entity_hierarchy` shall resolve a borrower's legal entity and ultimate parent as of a given `(as_of, known_as_of)` pair, reusing `enrichment.point_in_time.resolve_latest_known` unchanged so no-look-ahead holds without a second implementation. | must |
| REQ-003 | `CounterpartyLimit` shall gain optional legal-entity and ultimate-parent scope fields so one limit can aggregate every route whose borrower resolves into that entity; a limit carrying neither field shall behave exactly as today. | must |
| REQ-004 | A mapping shall be usable for hard aggregation only when it carries an `approval_reference`; `ownership_confidence` alone shall never authorize it (§22.9: Bloomberg proposes, internal credit/legal approves). An unusable mapping — unapproved, missing, or conflicting — shall reject the request with a structured `InputValidationError` naming the borrower, the limit, and which of the three reasons applies. | must |
| REQ-005 | That rejection shall be scoped to §22.9's own qualifier: it fires only where the mapping feeds a `hard` entity-scoped limit. A borrower with an unusable mapping that no `hard` entity-scoped limit could contain shall not fail the request, and neither shall a borrower whose routes are all ineligible or zero-capacity in this request. Because a *missing* mapping cannot be proven to fall outside any group, an unmapped borrower with allocatable routes shall fail whenever the request contains any `hard` entity-scoped limit at all. | must |
| REQ-006 | A non-`hard` entity-scoped limit shall degrade to a warning rather than a rejection, reusing `0011`'s warnings idiom — the sanctioned way to express "track group exposure advisorily." Unusable mappings shall be visible in the result regardless of whether they rejected the request (§22.9 requires both the failure and the data-quality disclosure). | must |
| REQ-007 | The system shall add an optional per-route `ExpectedEconomics` input carrying §22.5's coefficients (`take_up_probability`, `conditional_expected_days_active`, `return_hazard`, `repricing_hazard`, `recall_failure_probability`, `manufactured_payment_cost_usd`, `indemnification_capital_cost_usd`, `settlement_fail_cost_usd`, `relationship_value_or_cost_usd`), each accompanied by model version, calibration date, and an uncertainty measure. | must |
| REQ-008 | The system shall compute `expected_active_fraction_j = take_up_probability_j * conditional_expected_days_active_j / planning_horizon_days` per §22.5, clamped to `[0, 1]`, and expose it through `formulation.context.BuildContext` as a precomputed value — never estimated during compilation. | must |
| REQ-009 | `fee_revenue_coefficient` shall accept the expected-economics factor and additive cost terms as optional parameters, so `contribute()`, `attribute()`, `validation.solution_verifier`, and `reporting.explanations` all derive from one formula; omitting them shall reproduce today's contractual coefficient exactly. | must |
| REQ-010 | The system shall add a config switch (`ObjectiveConfig.economics_mode`, default `contractual`) selecting which economics drive the objective, per §22.5's required "switch allowing the simpler contractual value for controlled comparison". | must |
| REQ-011 | In the default `contractual` mode, when expected-economics estimates are supplied, the system shall report expected revenue **alongside** the contractual result without altering any allocation, quantity, or objective coefficient — a shadow comparison, not a solve. | must |
| REQ-012 | In `expected` mode, the system shall fail closed with a structured issue when any route lacks an `ExpectedEconomics` record, rather than silently mixing expected and contractual coefficients across routes. | must |
| REQ-013 | The result shall disclose which economics mode drove the objective and, per route, the model version and calibration date of every estimate used — satisfying §22.13's "validated predictions and uncertainty" boundary and giving a G3 review its evidence surface. | must |
| REQ-014 | The system shall add an optional per-inventory `DynamicBuffer` input carrying §22.7's five named components (`legal_minimum`, `pending_settlement_need`, `demand_uncertainty_quantile`, `event_recall_buffer`, `liquidity_horizon_buffer`), each in shares. | must |
| REQ-015 | `ReserveBufferConstraint` shall fold those components into its existing `max(...)` alongside today's `UtilizationPolicy` static buffers, so the binding buffer is the largest of all sources; absent a `DynamicBuffer`, its bound shall be byte-identical to today's. | must |
| REQ-016 | The result shall report, per inventory record whose availability bound is non-zero, which buffer component bound it — so a desk can see *why* shares were reserved rather than only that they were. | must |
| REQ-017 | The system shall provide golden tests proving: an expected-economics solve reallocates away from a route whose take-up probability is poor; the same request in `contractual` mode is unchanged; and a dynamic buffer larger than every static buffer binds. | must |

## Non-Functional Requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | Zero behavior change when nothing is supplied | Every existing test (326 passed pre-this-spec) continues to pass unchanged; a request with no `EntityRelationship`, `ExpectedEconomics`, or `DynamicBuffer`, under the default `contractual` mode, compiles to byte-identical variables, rows, bounds, and objective coefficients. |
| NFR-002 | Attribution reconciles in expected mode | `reporting.attribution.attribute_objective` reconstructs the solver's objective without raising `AttributionMismatchError` in both modes — guaranteed structurally by REQ-009's single-formula rule, and pinned by a test. |
| NFR-003 | The optimizer estimates nothing | No module under `src/inventory_optimizer` fits, trains, or infers a hazard/take-up/liquidity value; every such number enters as an input carrying its own model version and calibration date (§22.13). |
| NFR-004 | G3 stays un-granted | `expected` mode is off by default, is reachable only by an explicit config change, and is disclosed in every result it produces. Nothing in this repo asserts that the G3 review has happened. |
| NFR-005 | LP stays LP | Nothing in this spec introduces an integer, binary, or quadratic variable; `needs_mip`/`needs_qp` are untouched and a request using every feature here still compiles through `compile_lp`. |

## Acceptance Criteria

| ID | Given / When / Then | Covers |
| --- | --- | --- |
| AC-001 | Given two borrowers resolving to one ultimate parent and a parent-scoped limit, when solved, then the combined notional across both borrowers' routes respects the parent limit, and neither borrower alone is capped at it. | REQ-001, REQ-002, REQ-003 |
| AC-002 | Given a `hard` parent-scoped limit and a borrower whose entity mapping carries no `approval_reference`, when validated, then an `InputValidationError` names the borrower, the limit, and the unapproved reason — **even when `ownership_confidence` is 0.99**, since confidence never authorizes. | REQ-004 |
| AC-003 | Given an approved mapping with a *low* `ownership_confidence`, when validated, then it is usable for hard aggregation and the confidence is reported — approval supersedes the score. | REQ-004 |
| AC-004 | Given a borrower with an unusable mapping that no `hard` entity-scoped limit could contain, or whose routes are all ineligible/zero-capacity, when validated, then the request is **not** rejected; given a *missing* mapping for an allocatable borrower while the request contains any `hard` entity-scoped limit, then it is rejected. | REQ-005 |
| AC-005 | Given a **non-`hard`** entity-scoped limit and an unusable mapping, when solved, then a warning names it and the solve completes; and in every rejecting case above the unusable mapping is also visible in the result's data-quality surface. | REQ-006 |
| AC-006 | Given an entity relationship observed after the request's knowledge time, when the hierarchy is resolved, then that relationship is invisible — the same no-look-ahead guarantee `0011` established, inherited rather than reimplemented. | REQ-002 |
| AC-007 | Given a route with `take_up_probability = 0.5` and `conditional_expected_days_active` equal to half the horizon, when the expected factor is computed, then `expected_active_fraction` is `0.25`, and a factor computed outside `[0, 1]` is clamped. | REQ-008 |
| AC-008 | Given two otherwise identical routes differing only in take-up probability, when solved in `expected` mode, then allocation shifts to the higher-take-up route; given the same request in `contractual` mode, then allocation is unchanged from today's. | REQ-009, REQ-010, REQ-017 |
| AC-009 | Given a request with expected-economics estimates under the default `contractual` mode, when solved, then allocations and the objective are byte-identical to the same request with no estimates at all, and the expected-revenue comparison is reported separately. | REQ-011, NFR-001 |
| AC-010 | Given `expected` mode and a request where one route has no `ExpectedEconomics` record, when compiled, then it fails closed with a structured issue naming that route. | REQ-012 |
| AC-011 | Given an `expected`-mode solve, when objective attribution runs, then it reconciles without raising `AttributionMismatchError`, and the reported per-component value equals the hand-computed expected revenue. | REQ-009, NFR-002 |
| AC-012 | Given an `expected`-mode result, when inspected, then it names the mode and, per route, the model version and calibration date of each estimate used. | REQ-013, NFR-004 |
| AC-013 | Given an inventory record whose `liquidity_horizon_buffer` exceeds every static `UtilizationPolicy` buffer, when solved, then availability is bound by that component and the result names it as the binding one; given no `DynamicBuffer`, then the bound is byte-identical to today's. | REQ-014, REQ-015, REQ-016 |
| AC-014 | Given a request exercising entity aggregation, expected economics, and a dynamic buffer together, when compiled, then the problem is still an LP (no integer or quadratic variables) and `verification.passed` is true. | NFR-005 |
| AC-015 | Given the full existing suite (326 passed), when run after this spec's changes with nothing supplied, then all still pass unchanged. | NFR-001 |

## Data & Dependencies

- `domain/reference.py` (from `0011`) — gains `EntityRelationship`; `PointInTimeValue` reused
  unchanged.
- `enrichment/point_in_time.py` (from `0011`) — reused unchanged by REQ-002; this spec adds
  `enrichment/entity_hierarchy.py` beside it (a module `0011`'s own module-layout note reserved for
  R1).
- `ports/entity_data.py` and `adapters/bloomberg/entities.py` — the §22.2 port/adapter pair `0011`
  deliberately did not create because nothing consumed it yet. Created here, following `0011`'s
  synthetic-adapter pattern exactly.
- `domain/policies.py::CounterpartyLimit` — gains the optional entity scope (REQ-003).
- `components/constraints/counterparty.py` — resolves routes through the hierarchy instead of a
  single `borrower_id` lookup.
- `components/objective_terms/fee_revenue.py::fee_revenue_coefficient` — the single choke point
  (REQ-009), extended the way `0010` already extended it.
- `components/constraints/utilization.py::ReserveBufferConstraint` — one wider `max(...)`.
- `formulation/context.py::BuildContext` — gains the precomputed expected factors and resolved
  entity groups, the same slot `demand_caps`/`tier_caps` already occupy.
- `config/models.py::ObjectiveConfig` — gains `economics_mode`, following
  `allocation_stability_penalty`'s and `MultiPeriodConfig.daily_discount_rate`'s zero/default-off
  convention.
- `domain/results.py` — gains an additive, defaulted economics-disclosure section.
- `specs/engine_spec/TRACEABILITY.md` — `DAT-005` is this spec's evidence target; `LIM-*`/entity
  rows for §22.9 to be confirmed during implementation.

## Risks

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| RISK-001 | Expected economics changes what every reported dollar *means*. A reader comparing this quarter's optimizer output to last quarter's could attribute a modeling change to a book change. | Misread performance; a governance breach if expected numbers reach a desk as though they were contractual. | Off by default (REQ-010/NFR-004); every result names its mode (REQ-013); the default shadow mode (REQ-011) reports both side by side precisely so the difference is visible rather than substituted. |
| RISK-002 | Estimates arrive from an upstream that does not exist yet, so the feature cannot be exercised end to end against real data inside this repo — the same shape as `0011`'s synthetic-adapter limitation. | "Implemented" could be mistaken for "usable on the desk." | Stated in this spec's own Problem & Context and carried into `docs/handoff.md`; G3 remains explicitly un-granted (NFR-004); tests use hand-authored estimate fixtures with explicit fake model versions. |
| RISK-003 | An unresolved entity mapping, handled as a warning, would leave the borrower's routes **out** of the parent's `sum` — so a missing reference-data row silently relaxes a credit limit. The independent verifier cannot catch this: it recomputes rows from `CompiledProblem` and would report `verification.passed` for a row that is missing terms it was never told about. | A silent credit-limit breach reported as a successful solve — a control failure, not a modeling preference. | §22.9's fail-closed rule is implemented rather than softened (REQ-004), scoped to where it bites (REQ-005), with approval — not a vendor score — as the authority (REQ-004); AC-002 through AC-005 pin all four behaviors. No "conservative inclusion" escape hatch exists to erode it (Non-Goals); a desk wanting advisory group exposure sets `hard = False` and says so. |
| RISK-004 | `expected_active_fraction` multiplies revenue but not transition cost, so a low-take-up route could look cheap to churn. | Subtly wrong trade-off between revenue and turnover. | `plan.md` must state which terms the factor applies to and which it deliberately does not; AC-011's hand-computed check is written against the intended formula, so a drift shows up as a test failure rather than a plausible number. |
| RISK-005 | Bundling three §22 subsections in one spec makes for a large review. | Slower, lower-quality review; a defect hides in the volume. | The PWL piece is out (resolved question 2); the three remaining slices are independent — different files, different ACs — and sequenced as separate task groups so each can land and be reviewed on its own. |

## Assumptions & Open Questions

All four questions resolved by the owner (2026-09-15). Recorded here rather than deleted, so a
later reader sees what was decided and why.

- **Resolved — 1. Shadow/compare mode is the default**, with `expected` mode an explicit opt-in
  (REQ-010, REQ-011). G3 — "Expected-economics model promotion," owned by quant research + model
  risk + business — is precisely the approval for letting these numbers drive allocation, and this
  repo cannot grant it.
- **Resolved — 2. T24's piecewise-linear unwind cost is deferred to its own spec.** It is the only
  piece requiring new formulation machinery (segment variables), a convexity argument, and §14.3
  breakpoint disclosure. The dynamic *buffer* half of T24 stays here, where it is three lines
  inside an existing `max()`.
- **Resolved — 3. §22.9's fail-closed rule stands, refined by three sub-decisions:**
  - **3a — the rejection is narrowed to §22.9's own qualifier** ("fail closed *for hard
    aggregation*"): it fires only where the mapping feeds a `hard` entity-scoped limit (REQ-005). A
    bad mapping no hard entity-scoped limit could contain, or one for a borrower with no
    allocatable routes, does not stop the run. The *missing*-mapping case stays conservative
    because absence cannot prove the borrower falls outside a group.
  - **3b — internal approval, not vendor confidence, authorizes** hard aggregation (REQ-004).
    §22.9: Bloomberg "can propose the hierarchy, but internal credit/legal owners approve." A 0.99
    confidence score with no approval is unusable; an approved mapping with a low score is usable.
    Confidence screens and is reported; it never authorizes. This also matches NFR-003's posture —
    the optimizer estimates nothing, and it approves nothing either.
  - **3c — no "conservative inclusion" escape hatch** (Non-Goals). It is undefined for the most
    likely failure (a *missing* mapping has no candidate parent), it does not reliably preserve
    continuity (over-constraining can turn a clear rejection into a murkier infeasibility), and the
    capability already exists in cleaner form: `hard = False` states plainly that a control is
    advisory instead of dressing a weakened control as a safety feature.
  - Why this differs from `0011`, where status/calendar checks became warnings: **those checks
    annotate an answer the optimizer would have produced anyway; an entity mapping determines the
    content of a constraint.** Warn when the data only describes the solve; fail closed when it
    decides what the model is allowed to do.
- **Resolved — 4 (a documentation defect, not a design choice): the engine spec carries two
  incompatible "R" numbering schemes, and `0011` mis-tagged rows because of it.**
  `01_SPEC.md` §25 defines realism releases R0-R3 (R0 = data correctness, R1 = expected economics).
  `ROADMAPS.md` §2 defines a *different* R0-R8 delivery roadmap (R0 = portable package, R1 =
  verified baseline LP, **R3 = production data and schedule realism, T20-T24**).
  `TRACEABILITY.md`'s release column uses **`ROADMAPS.md`'s** numbering — which is why `DAT-005`
  reads "T23-T25 / R3-R5 / G3" rather than "R1". `0011` retagged `DAT-001`-`DAT-004`/`DAT-006`
  from `R3` to `R0` on §25's numbering, which was wrong in that column's own convention. **Already
  corrected**: the tags are restored and `TRACEABILITY.md` now carries a "Release Numbering"
  section naming which scheme the column uses.
- Assumption: `expected_active_fraction` multiplies the fee-revenue term only; the additive cost
  coefficients (manufactured payment, indemnification capital, settlement fail, relationship) enter
  as separate per-route linear costs. `plan.md` pins the exact formula (RISK-004).
- Assumption: reinvestment income stays out (Non-Goals), so §22.5's `(f_j * s_j + r_j * h_j)`
  reduces to the existing `(f_j * s_j - c_j)` with the expected factor applied.

## Exceptions

None recorded.
