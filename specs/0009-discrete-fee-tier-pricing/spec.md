# Spec: Discrete fee-tier pricing (joint fee/quantity, Phase 5 item 1)

- **ID:** 0009-discrete-fee-tier-pricing
- **Status:** Draft
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code)
- **Approver:**
- **Last updated:** 2026-09-05

> WHAT and WHY only. No implementation detail — that belongs in `plan.md`.

## Problem & Context

Today the borrower fee is an **input**, never a decision. `LoanRoute.fee_rate` is a fixed field;
`elasticity/` turns that fee into a demand cap once, before model build (§12.1: "Elasticity is
preprocessing, not an LP decision"); and the LP then chooses only *how much* to lend at that
already-fixed price. The desk question "would we make more by repricing this name?" cannot be
answered by the optimizer at all — it can only be explored by re-running whole scenarios at
hand-picked fees.

`00_PLAN.md`'s Phase 5 item 1 names the general version of this ("joint fee/quantity demand curves
through an optional nonlinear backend or sequential convex approximation"), and `01_SPEC.md` §12.5
explains exactly why it is hard: continuous fee `f_g` with `q_g = D_g(f_g)` produces a **bilinear**
revenue term `f_g * q_g`, which "belongs in an optional nonlinear formulation or a documented
sequential/piecewise approximation. It must not be disguised as an LP."

**`01_SPEC.md` §12.4 already specifies the discrete form of exactly this, normatively**, and it has
never been built:

```text
For candidate fee tiers k in K(g):
  binary z_gk selects a price tier;
  continuous q_gk is allocated quantity at that tier;
  precomputed D_gk = D_g(f_gk) is the tier capacity.

  sum_k z_gk <= 1
  0 <= q_gk <= D_gk * z_gk
  route allocations at tier k sum to q_gk

The objective uses f_gk * q_gk. Because each f_gk is a constant, the formulation is linear MIP.
```

This spec builds that. It is the *discrete* answer to Phase 5 item 1 — §12.5's own sanctioned
"documented piecewise approximation" — and it simultaneously closes work three other places in this
repo deferred for want of a fee-tier concept:

- `00_PLAN.md` Phase 3 item 2 ("discrete rate-ladder selection for optional price
  recommendations"), which `specs/0006-mip-business-rules/` declared a Non-Goal because it "needs a
  wholly new domain concept (a set of candidate fee tiers per demand group)";
- §14.1's seventh MIP trigger ("one fee tier per demand group"), likewise unbuilt; and
- `validation/reconciliation.py::check_demand_group_fee_consistency`, whose own error message
  already tells users to "use distinct demand groups or **the discrete pricing MIP** for genuinely
  different borrower prices" — a facility that does not yet exist.

**Why discrete rather than a true nonlinear backend.** §14.3 states this repo's own preference
("Prefer piecewise-linear approximations when they preserve acceptable accuracy"), and every
`01_SPEC.md` reference to joint pricing lists "PWL MIP or NLP" in that order. Mechanically the
discrete form keeps a property a true NLP cannot offer: because each `f_gk` is a constant, the
model stays a **linear MIP**, so HiGHS's branch-and-bound either proves global optimality or
reports `FEASIBLE_LIMIT` — the same honest status contract Phase 3 already established. A
non-convex NLP would only ever return a *local* optimum, which §14.4 itself requires be labeled as
such ("a result status that distinguishes local from global optimality"), and which is materially
harder to validate for a desk. A true `NonlinearSolverBackend` remains available later for the
continuous case; nothing here forecloses it.

**This is discrete candidate selection, not interpolation.** Classic piecewise-linear approximation
introduces interpolation error between breakpoints. Here `D_gk` is evaluated by the *real*
elasticity curve at each candidate fee, exactly — so within the candidate set the model is exact,
and the only approximation is which prices were offered as candidates. That distinction matters for
§14.3's disclosure requirement and is stated plainly in the results rather than glossed.

## Goals

- One new domain concept: an optional set of **candidate fee tiers** per demand group, absent by
  default. A group with no tiers behaves exactly as it does today.
- Precompute each tier's capacity `D_gk = D_g(f_gk)` by calling the **existing, unchanged**
  `elasticity.evaluate_demand_cap` once per candidate fee — the same function that already computes
  today's single cap.
- A new MIP constraint component implementing §12.4's tier-selection structure (at most one tier
  per group; quantity at an unselected tier is zero; route quantities decompose across tiers), and
  a new objective term valuing the selected tier's fee.
- Route-level economics preserved: §12.2 notes "Lender revenue shares may still produce different
  net route economics", so revenue must be computed per route at the selected tier, not by one
  group-level aggregate (see `plan.md`'s deviation note on §12.4's `q_gk` sketch).
- Auto-routing: a request with fee tiers is a MIP request, handled by the existing
  `formulation.mip.compile_mip` and `facade.InventoryOptimizer.optimize`'s existing dispatch, with
  `compile_lp` failing closed exactly as it already does for every other discrete trigger.
- Result reporting that satisfies §14.3's disclosure duty: which tiers were offered, which was
  selected, and the resulting fee — so a desk can see the recommendation *and* the menu it came
  from.
- Golden tests proving the optimizer genuinely reprices: a fixture where the elastic revenue
  optimum is a *different* tier than the current fee, and one where holding the current fee wins.

## Non-Goals

- **A true `NonlinearSolverBackend`, continuous fee optimization, or sequential convex
  approximation** — §14.4's literal route. Deferred deliberately (see Problem & Context); this
  spec's discrete form is §12.5's own sanctioned alternative, and a later continuous spec can reuse
  the same domain field as its candidate seed.
- **Interpolating between tiers** — no segment/SOS2 machinery, no synthetic fees between
  candidates. The model evaluates only the fees supplied.
- **Choosing the candidate tiers for the caller** — no tier-grid generation, no "search around the
  current fee" heuristic. The desk (or an upstream pricing service) supplies the menu; inventing
  candidate prices inside the optimizer would be pricing policy hiding in a solver.
- **Reporting a distance-to-continuous-optimum error bound** — computing it means optimizing the
  continuous revenue curve, i.e. the very nonlinear problem this spec avoids. The results disclose
  the candidate grid and the selection instead, which is the honest statement of what was actually
  considered. Tracked as a follow-up if a continuous spec ever lands.
- **Per-route fee tiers** — tiers are a demand-group (borrower/security) concept, matching §12.2's
  aggregation rule. Routes in a group continue to share one borrower fee.
- **Changing `LoanRoute.fee_rate`'s meaning or `check_demand_group_fee_consistency`** — the route
  fee remains the current/reference borrower price and must still be uniform within a group; tiers
  are the *candidate* prices considered against it.
- **Multi-period or scenario-tree pricing** — `00_PLAN.md` Phase 5 item 2, untouched.

## Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| REQ-001 | The system shall add an optional candidate-fee-tier field to `domain.demand.DemandForecast` (empty by default), validated as strictly positive, strictly increasing, and free of duplicates. | must |
| REQ-002 | `formulation.context.build_context` shall precompute, for each demand group with tiers, one `EvaluatedDemand` per candidate fee via the unchanged `elasticity.evaluate_demand_cap`, exposing them to components alongside today's single cap. | must |
| REQ-003 | The system shall introduce per-tier binary selection variables and per-route-per-tier continuous quantity variables for tiered groups only, contributing zero variables for every untiered group. | must |
| REQ-004 | A new MIP constraint component shall compile §12.4's structure: at most one tier selected per group; each route's per-tier quantity bounded by that tier's capacity and zeroed unless the tier is selected; and each route's total quantity equal to the sum of its per-tier quantities. | must |
| REQ-005 | A new objective component shall value the selected tier's fee per route, honoring each route's own `revenue_share` and `variable_cost_rate`, and shall reconcile exactly under `reporting.attribution.attribute_objective`. | must |
| REQ-006 | `formulation.compiler_support.needs_mip` shall report `True` for a request carrying fee tiers, so `compile_lp` fails closed with a structured issue and `facade.InventoryOptimizer.optimize` routes to `compile_mip` automatically — both by the existing mechanisms, not new ones. | must |
| REQ-007 | The result shall report, per tiered demand group, the candidate fees offered, the selected fee, and the quantity filled at it, satisfying §14.3's duty to record breakpoints and disclose that integer variables were introduced. | must |
| REQ-008 | Composite variable scope identifiers used for per-route-per-tier variables shall remain reversible: the system shall reject any identifier containing the reserved separator rather than producing an ambiguous key. | must |
| REQ-009 | The system shall provide golden tests covering: a group that reprices to a higher-fee tier, a group that reprices to a lower-fee tier to win volume, a group where the incumbent fee wins, and confirmation that at most one tier is ever selected. | must |
| REQ-010 | The existing `demand_cap` component shall skip demand groups carrying tiers — whose capacity REQ-004 enforces per tier instead — and shall behave exactly as today for every untiered group. | must |

## Non-Functional Requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | No behavior change for untiered requests | Every existing test continues to pass unchanged (193 pre-this-spec). A `DemandForecast` without tiers produces exactly today's variables, rows, and results — the new variable blocks are empty, contributing zero columns, the same property `specs/0006-mip-business-rules/` relied on for `z`/`n`. |
| NFR-002 | Global optimality preserved | Because every `f_gk` is constant, the compiled problem stays a linear MIP; the existing status normalization continues to distinguish proven-optimal from `FEASIBLE_LIMIT`, and no result is ever labeled optimal when it is not. |
| NFR-003 | Baseline components changed only where the mathematics requires it | `fee_revenue`, `inventory_balance`, and `transition_identity` are reused **unchanged** — the new revenue term contributes the *delta* from the reference fee rather than teaching `fee_revenue` about tiers. `demand_cap` is the one exception and must skip tiered groups: its row caps quantity at the *reference* fee's demand, which is wrong the moment a cheaper tier is selected (a lower fee implies higher demand). That skip is guarded on the tiered-group set, so it is inert for every untiered request. |
| NFR-004 | Honest disclosure | The result states the candidate menu and the selection; nothing implies the optimizer searched prices it was never given. |

## Acceptance Criteria

| ID | Given / When / Then | Covers |
| --- | --- | --- |
| AC-001 | Given a demand group with candidate fees and an elasticity making a higher fee more profitable despite lower volume, when solved through the facade, then the selected tier is that higher fee, exactly one tier is selected, and `verification.passed` is true. | REQ-001 through REQ-005 |
| AC-002 | Given the same group with an elasticity making a lower fee more profitable through volume, when solved, then the selected tier is the lower fee. | REQ-004, REQ-005 |
| AC-003 | Given candidate fees among which the incumbent `route.fee_rate` is optimal, when solved, then the incumbent tier is selected and total objective equals the untiered solve's objective within tolerance. | REQ-005, NFR-001 |
| AC-004 | Given a tiered request, when compiled via `compile_lp` directly, then it raises `InputValidationError` naming the demand group and its tiers, rather than silently pricing at the incumbent fee. | REQ-006 |
| AC-005 | Given a tiered request solved through the facade, when the result is inspected, then it reports for each tiered group the candidate fees offered, the selected fee, and the filled quantity. | REQ-007, NFR-004 |
| AC-006 | Given a tiered request, when objective attribution runs, then it reconciles to the solver's objective without raising `AttributionMismatchError`, and the pricing term's value equals the hand-computed revenue delta between the selected and reference fees. | REQ-005 |
| AC-007 | Given a `DemandForecast` constructed with duplicate, unordered, or non-positive candidate fees, then construction raises a validation error. | REQ-001 |
| AC-008 | Given a route or demand-group identifier containing the reserved separator, when a tiered request is compiled, then it is rejected with a structured issue rather than producing an ambiguous variable key. | REQ-008 |
| AC-009 | Given every pre-existing test (193, pre-this-spec), when run after this spec's changes, then all still pass unchanged, and an untiered request compiles to byte-identical variable and row indexes. | NFR-001 |
| AC-010 | Given a tiered group whose routes carry different `revenue_share` values, when solved, then each route's revenue is valued at its own share against the selected tier fee — not at a single group-level rate. | REQ-005 |

## Data & Dependencies

- `domain.demand.DemandForecast` — gains the optional candidate-tier field (REQ-001); every other
  field unchanged.
- `elasticity.evaluate_demand_cap` / `EvaluatedDemand` (T06) — reused unchanged, called once per
  candidate fee instead of once per group.
- `formulation.context.build_context` (T12) — gains the per-tier cap map and the tiered-group sets
  driving the new variable blocks.
- `formulation.mip.compile_mip`, `formulation.compiler_support.needs_mip`, and the `z`-style
  variable-block pattern (T15, `specs/0006-mip-business-rules/`) — extended, not redesigned.
- `components.objective_terms.fee_revenue` (T08) — reused unchanged; the new term contributes only
  the delta from the reference fee (NFR-003).
- `domain.results.OptimizationResult` — gains an additive, defaulted pricing section (REQ-007).
- `solvers.highs.HighsBackend` (T09) — already MIP-capable; no changes.
- `specs/spec002/TRACEABILITY.md` rows `LP-004` (elasticity-adjusted demand caps) and `LP-009`
  (MIP/QP/PWL/NLP capability gating) — this spec's evidence targets.

## Risks

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| RISK-001 | Per-route-per-tier quantity variables multiply the model: a tiered group with `J` routes and `K` tiers adds `J*K` continuous variables plus `K` binaries. | A desk that tiers many groups with long fee ladders could slow solves materially versus today's LP. | Tiers are strictly opt-in per demand group and contribute nothing when absent (NFR-001), so the cost is paid only where repricing is actually being evaluated. `plan.md` proposes a `slow`-marked scale test establishing the shape of the growth, following `specs/0005-test-hardening/`'s benchmark precedent. |
| RISK-002 | Composite `(route, tier)` variable scope identifiers break the reversible index mapping if a domain ID contains the separator. | An ambiguous key would silently mis-map a variable to the wrong route — a correctness failure, not a cosmetic one. | REQ-008 makes it a validated, fail-closed rejection rather than a convention nobody enforces; AC-008 pins the behavior. |
| RISK-003 | The optimizer recommending a *price* is a materially different act from recommending a *quantity*: it may cross desk pricing authority, client agreements, or approval workflows that today assume fees are given. | A repricing recommendation could be actioned as though it carried the same authorization as an allocation recommendation. | `GOV-003` already holds every result to being "recommendations requiring downstream authorization", and §12.4 requires "one-price-per-group behavior must be explicit". REQ-007's disclosure (menu plus selection) is what makes the price recommendation reviewable rather than implicit. Flagged here so approval treats pricing output as its own governance question, not a free rider on allocation output. |
| RISK-004 | Discrete tiers can only be as good as the menu supplied; a desk may read "optimal" as "optimal price" rather than "best of the prices offered". | Overstated confidence in a recommendation that never considered the true continuous optimum. | The Problem & Context distinction (exact-within-candidates, not interpolated) is carried into the result surface (REQ-007) and the Non-Goals: the optimizer reports the menu it was given and never generates candidates itself. |

## Assumptions & Open Questions

- Assumption: tiers belong to the demand group (borrower × security), not the route, matching
  §12.2's aggregation rule. Routes in a tiered group continue to share one borrower fee — the
  selected one.
- Assumption: `sum_k z_gk <= 1` (§12.4's literal inequality) rather than `= 1`, so "sell nothing to
  this group" stays feasible; a group whose every tier is uneconomic can simply go unselected with
  all its route quantities at zero.
- Assumption: `route.fee_rate` remains the incumbent price and continues to anchor
  `fee_revenue`'s baseline, with the new term carrying the delta (NFR-003). This keeps attribution
  readable as "revenue at today's price, plus what repricing added".
- Open question: whether the selected fee should also flow back into
  `reporting.explanations`'s reason codes (e.g. a `REPRICED_TO_TIER` code) — `ReasonCode` has 24
  values and none covers price selection. Deferred; `plan.md` proposes reporting the selection
  structurally first and only adding a reason code once a desk asks for it in narrative form.
- Open question: whether a future continuous-fee spec should seed its search from this spec's
  candidate field or introduce its own bounds. Deferred until such a spec exists.

## Exceptions

None recorded.
