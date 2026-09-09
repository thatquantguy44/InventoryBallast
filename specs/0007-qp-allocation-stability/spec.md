# Spec: QP allocation-stability penalty (Phase 4)

- **ID:** 0007-qp-allocation-stability
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted and implemented by Claude Code)
- **Approver:** Joshua Lutkemuller, CFA ("Start working on Phase 4" — approved proceeding with Phase 4 as the next priority identified at the close of `0006-mip-business-rules/`)
- **Last updated:** 2026-09-05

> WHAT and WHY only. No implementation detail — that belongs in `plan.md`.

## Problem & Context

`specs/engine_spec/01_SPEC.md` §14.2 ("Convex QP extensions") and `00_PLAN.md`'s Phase 4 ("QP and
advanced objective terms") define a family of convex quadratic objective terms the baseline
continuous LP (T08) and MIP (T15) cannot represent: squared deviation from current allocations,
borrower/security concentration penalties, covariance-weighted revenue/recall risk, and smooth
utilization-target deviations. `00_PLAN.md`'s own exit gate: "the LP remains the default and QP
behavior is capability-gated and regression-tested."

Of the four candidate terms, only **squared deviation from current allocations** ("allocation
stability") is groundable in this repo today with no new domain concept: every `LoanRoute` already
carries `current_quantity_shares` (T04), and the baseline formulation already has `inc_j`/`dec_j`
transition variables (T08) whose difference is exactly `q_j - current_quantity_shares_j` by the
transition identity. The other three candidates each need data this repo has no source for yet
(a borrower/security concentration limit shape, a covariance matrix, a utilization-target
config) — deferred, matching how `specs/0006-mip-business-rules/` scoped Phase 3 to the triggers
that were actually groundable rather than everything §14.1 names.

`CompiledProblem.quadratic_objective: SparseMatrix | None` and `Formulation.QP`/
`Capability.CONTINUOUS_QP` have existed since Phase 0A's original scaffold but were never
populated or read by anything — this spec is the first to do either. `ScalingMetadata` (Section
20.3) has existed the same way, "so a later scaling pass does not need a `CompiledProblem` shape
change" (its own docstring) — this spec is that later pass, for a concrete, empirically-motivated
reason (see below), not speculatively.

**A real numerical finding drove this spec's design.** The most direct way to express "penalize
`(q_j - q0_j)^2`" is a 2x2 Hessian block on `inc_j`/`dec_j` (`[[lambda,-lambda],[-lambda,lambda]]`)
— exactly zero at the unchanged baseline, no new `CompiledProblem` field needed. Reconstructing
this exact model directly against the pinned `highspy` (1.15.1) version, bypassing this repo's own
compiler entirely, showed HiGHS's QP active-set method **stalls indefinitely** (millions of
iterations, no convergence) whenever the Hessian's magnitude sits several orders below the rest of
the model's coefficients (confirmed reproducible down to a specific numeric threshold in a
four-variable, hand-built model) — a real solver-robustness limit of the pinned backend version,
not a modeling defect (verified: the identical stall reproduces with a diagonal Hessian on `q_j`
directly too, and disappears entirely once the whole objective is uniformly rescaled by a single
positive constant, which never changes the optimal `x`). Section 14.2 anticipates exactly this
class of finding: "Continuous QP support is backend/version capability-gated. ... The compiler
reports any regularization added." This spec's scaling pass is the concrete instance.

## Goals

- One new convex QP objective term, `components.objective_terms.allocation_stability`: a
  desk-level coefficient (`config.objective.allocation_stability_penalty`, USD per share-squared)
  penalizing `(q_j - current_quantity_shares_j)^2` for every route, contributed entirely via the
  existing `inc_j`/`dec_j` transition variables (zero at the unchanged baseline, no new
  `CompiledProblem` field).
- A new `formulation.qp.compile_qp(request, config) -> CompiledProblem` that reuses every
  already-implemented baseline constraint/objective component unchanged, adding only the new term,
  and validates the assembled quadratic matrix is positive semidefinite within tolerance (Section
  14.2's literal requirement).
- `formulation.lp.compile_lp` shall **reject**, not silently ignore, a request compiled under a
  config with a positive `allocation_stability_penalty` — the same fail-closed precedent
  `specs/0006-mip-business-rules/` set for MIP triggers.
- `compile_mip`/`compile_qp` shall each reject a request/config combination needing the *other*
  compiler's own trigger too — Section 14.2: "Mixed-integer quadratic behavior requires a separate
  capable backend or an explicitly documented decomposition ... must never be labeled globally
  optimal when it is not." Neither exists yet, so combining fails closed rather than silently
  picking one.
- `facade.InventoryOptimizer.optimize()` shall route to `compile_qp` automatically whenever a
  request needs it, with no caller action required, alongside the existing MIP auto-routing.
- `solvers.highs.HighsBackend` gains `Capability.CONTINUOUS_QP` and solves real QP models (a
  `highspy.HighsModel` with a Hessian), reading `CompiledProblem.scaling` to keep HiGHS's QP
  solver numerically reliable — internally only; every other subsystem (`validation.
  solution_verifier`, `reporting.attribution`) continues to see true, unscaled USD values exactly
  as before.
- `validation.solution_verifier.verify_solution`'s independent objective reconstruction includes
  the quadratic term — otherwise every correct QP solve would fail this check by exactly its own
  quadratic magnitude (a real, load-bearing gap this spec closes, not a hypothetical one).
- Golden tests proving the penalty measurably pulls allocation toward the current book, correct
  attribution/verification/shadow-price reporting for a real QP solve, and a scale/performance
  smoke test (`00_PLAN.md` Phase 4 item 3: "Add positive-semidefinite validation and scaling
  tests").

## Non-Goals

- **Borrower/security concentration penalty, covariance-weighted revenue/recall risk, smooth
  utilization-target deviations** (§14.2's other three candidate terms) — each needs a new domain
  concept this repo has no source for yet (concentration limit shape, covariance matrix,
  utilization-target config). Deferred pending a real need, matching `0006`'s own scoping
  precedent.
- **Combining the QP penalty with MIP triggers in the same compile** (mixed-integer QP) — Section
  14.2 explicitly requires "a separate capable backend or an explicitly documented decomposition,"
  neither of which exists; this spec fails the combination closed rather than building either.
- **A general, auto-detected numerical scaling pass for LP/MIP** — `compile_lp`/`compile_mip`
  continue exactly as before (`ScalingMetadata.applied=False`, unchanged); scaling is applied only
  by `compile_qp`, only because a concrete, reproduced solver limitation motivates it.
- **A fixed route-activation-cost or discrete rate-ladder objective shape re-expressed as QP** —
  those remain `specs/0006-mip-business-rules/`'s own deferred Non-Goals, unrelated to this spec.
- **§14.3 piecewise-linear, §14.4 nonlinear extensions** — `00_PLAN.md`'s own Phase 5, not Phase 4.
  Untouched.
- **Wiring `config.formulation.mode`** (an existing, still-unused Phase 0A field) as a manual
  formulation override — this spec keeps the established auto-detection precedent (`needs_mip`/
  `needs_qp`) from `0006`; the field stays exactly as unused as it was before this spec.

## Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| REQ-001 | The system shall add `config.models.ObjectiveConfig.allocation_stability_penalty: float` (default `0.0`, `ge=0.0`) and a new objective component contributing `-(lambda/2)*(inc_j - dec_j)^2` per route via `inc_j`/`dec_j`'s existing 2x2 quadratic block. | must |
| REQ-002 | The system shall provide `formulation.qp.compile_qp(request, config) -> CompiledProblem`, composing the existing `REQUIRED_CONSTRAINTS`/`REQUIRED_OBJECTIVES` baseline components unchanged plus REQ-001's term, and validate the assembled `quadratic_objective` matrix is positive semidefinite within tolerance, rejecting the compile with a structured issue if not. | must |
| REQ-003 | `formulation.lp.compile_lp` shall raise a structured `InputValidationError` (code `QP_REQUIRED`) rather than silently compiling a request under a config with `allocation_stability_penalty > 0`. | must |
| REQ-004 | `formulation.mip.compile_mip` and `formulation.qp.compile_qp` shall each raise a structured `InputValidationError` (code `MIQP_UNSUPPORTED`) when the *other* compiler's own trigger is also present (a MIP-triggering route/policy together with a positive `allocation_stability_penalty`). | must |
| REQ-005 | `facade.InventoryOptimizer.optimize()` shall detect whether a request/config needs QP treatment (REQ-003's same criterion) and call `compile_qp` instead of `compile_lp` automatically, requiring no caller action, alongside the existing MIP auto-routing. | must |
| REQ-006 | `solvers.highs.HighsBackend` shall declare `Capability.CONTINUOUS_QP` and solve a `CompiledProblem` with a non-`None` `quadratic_objective` via a `highspy.HighsModel`/`HighsHessian`, reading `CompiledProblem.scaling` to rescale its own HiGHS-facing translation only (never `CompiledProblem`'s own stored arrays) and dividing the solved objective/duals back down by the same factor before returning a `SolverResult`. | must |
| REQ-007 | `validation.solution_verifier.verify_solution`'s objective reconstruction shall include the quadratic term (sense-signed) whenever `CompiledProblem.quadratic_objective` is set. | must |
| REQ-008 | `formulation.qp.compile_qp` shall compute and attach `CompiledProblem.scaling` (Section 20.3) whenever a quadratic term exists, so `solvers.highs.HighsBackend` can keep the pinned QP solver numerically reliable (see Problem & Context's empirical finding). | must |
| REQ-009 | The system shall provide golden tests proving the configured penalty measurably pulls the optimal quantity toward the current book across a low/moderate/high coefficient sweep, plus tests for REQ-003/REQ-004's rejections, REQ-002's PSD validation (accept and reject cases), correct attribution reconciliation, and correctly-scaled (true USD) shadow prices for a real QP solve. | must |
| REQ-010 | `formulation.compiler_support.resolve_component` shall reject a resolved component whose registered `formulations` metadata does not include the caller's target formulation, closing a pre-existing gap (nothing enforced Section 15.1's "declare formulations" before this spec) that this work surfaced while adding a QP-only component alongside existing LP/MIP-only ones. | must |

## Non-Functional Requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | The LP remains the default; zero behavior change for existing LP/MIP requests | Every existing test continues to pass unchanged (172 total, pre-this-spec) — `allocation_stability_penalty`'s `0.0` default means `needs_qp` never triggers for a config that predates this field, and `compile_lp`/`compile_mip` apply no scaling (`ScalingMetadata.applied=False`, unchanged). |
| NFR-002 | QP behavior is capability-gated and regression-tested | `HighsBackend.capabilities` only claims `Capability.CONTINUOUS_QP` once genuinely exercised end to end (compile → solve → verify → attribute) by this spec's own tests, not merely declared. |
| NFR-003 | No silent scaling drift | `CompiledProblem.linear_objective`/`quadratic_objective` stay in true USD units regardless of `scaling.applied`; only `solvers.highs` ever reads `scaling.objective_scale_usd`, so `validation.solution_verifier`/`reporting.attribution` need zero scaling-awareness changes beyond REQ-007's quadratic-term inclusion itself. |

## Acceptance Criteria

| ID | Given / When / Then | Covers |
| --- | --- | --- |
| AC-001 | Given a route with `current_quantity_shares=50`, `maximum_quantity_shares=100`, positive fee economics favoring growth to `100`, and `allocation_stability_penalty=0.0`, when solved via the facade, then the post-quantity is `100` (LP-equivalent behavior, penalty inactive). | NFR-001 |
| AC-002 | Given the same route with `allocation_stability_penalty` set to a moderate positive value, when solved via the facade, then the post-quantity is strictly between `50` and `100`, matching the closed-form optimum `q0 + fee_coefficient/lambda` (clamped to bounds) to within solver tolerance. | REQ-001, REQ-002, REQ-005 |
| AC-003 | Given the same route with a very large `allocation_stability_penalty`, when solved, then the post-quantity is approximately `50` (the penalty dominates, pulling fully back to the current book). | REQ-001, REQ-002, REQ-005 |
| AC-004 | Given any request with `allocation_stability_penalty > 0`, when compiled via `compile_lp` directly, then it raises `InputValidationError` with code `QP_REQUIRED` naming `config.objective.allocation_stability_penalty`, rather than silently ignoring it. | REQ-003 |
| AC-005 | Given a request with both an `all_or_none` route and a positive `allocation_stability_penalty`, when compiled via `compile_mip` or `compile_qp` (either one, directly), then it raises `InputValidationError` with code `MIQP_UNSUPPORTED`. | REQ-004 |
| AC-006 | Given `formulation.qp_support.validate_psd` called directly with a hand-built symmetric matrix, when the matrix is positive semidefinite, then it returns no issues; when it is not (a known indefinite 2x2 example), then it returns exactly one `QP_NOT_POSITIVE_SEMIDEFINITE` issue — for both the dense (small-matrix) and sparse `eigsh` (large-matrix) code paths. | REQ-002 |
| AC-007 | Given AC-002's solved result, when `reporting.attribution.attribute_objective` runs (via the facade's own `build_optimization_result` call), then it does not raise `AttributionMismatchError` and the `allocation_stability` component's independently-recomputed value matches `-(lambda/2)*(q-q0)^2` exactly. | REQ-007, REQ-009 |
| AC-008 | Given AC-002's solved result, when its constraint activities are inspected, then at least one row has a non-`None` `dual_value`, and that value's order of magnitude matches the fee coefficient (i.e., it was correctly divided back out of HiGHS's internally-scaled units, not left inflated by the scale factor). | REQ-006, REQ-008 |
| AC-009 | Given every pre-existing test in the suite (172, pre-this-spec), when run after this spec's changes, then all still pass unchanged. | NFR-001 |
| AC-010 | Given a moderate-scale QP request (hundreds of routes, one uniform desk-level penalty applied to all of them per REQ-001's own design), when compiled and solved, then it reaches `OPTIMAL` well within a bounded time ceiling (`00_PLAN.md` Phase 4 item 3's "scaling tests"), `@pytest.mark.slow`-marked per `specs/0005-test-hardening/`'s own precedent. | REQ-008 |

## Data & Dependencies

- `domain.loans.LoanRoute.current_quantity_shares` (already implemented, T04) — read-only input to
  REQ-001.
- `config.models.InventoryOptimizerConfig` — gains a new `objective: ObjectiveConfig` section
  (Section 8.2's own docstring named this as a deferred section since Phase 0A); every other
  section unchanged.
- `formulation.lp.compile_lp`'s `REQUIRED_CONSTRAINTS`/`REQUIRED_OBJECTIVES` and the baseline
  components themselves (T08) — reused unchanged by `compile_qp`.
- `formulation.compiled.CompiledProblem.quadratic_objective`/`scaling` (Phase 0A scaffold fields,
  never populated before this spec).
- `solvers.highs.HighsBackend`, `ports.solver.SolverOptions`/`SolverResult` (T09) — gains QP
  capability and Hessian/scale handling; LP/MIP code paths unchanged.
- `validation.solution_verifier.verify_solution` (T10) — gains quadratic-term reconstruction.
- `facade.InventoryOptimizer` (T12) — gains the auto-routing logic (REQ-005).
- `formulation.compiler_support.resolve_component` (T15) — gains the formulation-membership check
  (REQ-010).
- `specs/engine_spec/TRACEABILITY.md`'s `LP-009` row — this spec's evidence target, extending the MIP
  portion `0006` already moved to `IMPLEMENTED` (PWL/NLP stay `SPECIFIED`).

## Risks

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| RISK-001 | HiGHS's QP active-set method (pinned `highspy` 1.15.1) is empirically fragile for small-Hessian-relative-to-bounds models; the scaling fix this spec applies was tuned against the specific reproduced case, not proven robust for every conceivable coefficient combination a desk might configure. | An unusually-scaled real request could still hit the same stall despite this spec's scaling pass, silently degrading to `FEASIBLE_LIMIT` at the configured time limit rather than `OPTIMAL`. | `FEASIBLE_LIMIT` is never mislabeled `OPTIMAL` (existing, unchanged status-normalization guarantee) — a stalled solve is reported honestly, not silently accepted as globally optimal. AC-010's scale test and this risk entry are the documented follow-up trigger for revisiting the scaling rule if a real desk config ever reproduces a stall. |
| RISK-002 | The allocation-stability term is a uniform, desk-wide coefficient, not per-route — a single misconfigured large value could unexpectedly suppress economically-favorable reallocation across every route in a request, not just one. | A desk could get a materially worse (over-conservative) recommendation without an obvious signal beyond the attribution breakdown. | `reporting.attribution`'s `allocation_stability` component entry already surfaces the penalty's exact USD cost per solve (REQ-007/AC-007) — visible in every result, not hidden; per-route coefficients are a Non-Goal for this pass, tracked as a follow-up if ever needed. |
| RISK-003 | `resolve_component`'s new formulation-membership check (REQ-010) is a behavior change to a function every existing compiler already calls. | A desk config that (incorrectly) enabled a component for the wrong formulation via `config.desk.enabled_components` would newly fail where it previously silently ran. | Verified every existing baseline/MIP component already declares its correct, complete formulation set (inspection plus the full 172-test suite passing unchanged) — this is purely additive protection against a configuration mistake, not a change to any component's own declared scope. |

## Assumptions & Open Questions

- Assumption: `allocation_stability_penalty` is a single, desk-wide (config-level) coefficient
  applied uniformly to every route, not a per-route or per-policy field — matching how the term is
  introduced in `01_SPEC.md` §14.2 as an objective-shaping desk decision, unlike Phase 3's
  per-route/per-policy MIP triggers.
- Assumption: the scaling rule (rescale so the assembled Hessian's largest-magnitude entry becomes
  exactly `1.0`) is a reasonable, general heuristic for this specific empirically-observed failure
  mode, not a proof of numerical robustness for every possible future QP term's coefficient range.
  Tracked via RISK-001.
- Open question: whether a future second QP objective term (e.g., a concentration penalty) should
  share this spec's scaling rule unchanged, or whether the rule needs to account for multiple
  terms' combined coefficient range. Deferred until a second QP term actually exists.

## Exceptions

None recorded.
