# Spec: Result, objective attribution, and explainability (T11)

- **ID:** 0002-result-attribution-explainability
- **Status:** Draft
- **Author:** Joshua Lutkemuller (with `problem_formulation` / `solver_diagnostics_sensitivity` agent review)
- **Approver:**
- **Last updated:** 2026-09-04

> WHAT and WHY only. No implementation detail — that belongs in `plan.md`.

## Problem & Context

`specs/spec002/01_SPEC.md` §18 defines the full `OptimizationResult` reporting
layer: identity/status, allocations, balances, economics, demand, schedules,
collateral, desk, sources, constraints, solver diagnostics, verification,
warnings, and platform references (§18.1); per-component objective attribution
reconciled to the verified solver objective (§18.2); deterministic decision
explanations via `ReasonCode` (§18.3); and LP shadow prices, correctly labeled
and never mislabeled as MIP duals (§18.4).

None of this is built yet. `domain/results.py`'s `OptimizationResult` only
implements the Identity and Status sections by design (its own docstring says
"the solver-derived sections are added by T09-T11"). Every registered
objective component's `attribute()` method — `fee_revenue.py`,
`transition_cost.py` — raises `NotImplementedError("objective attribution
lands with T11")`. `components/interfaces.py` documents `VerifiedSolution` and
`ObjectiveAttribution` as "independent-verifier (T10) and result-attribution
(T11) types not introduced yet." T10's `verify_solution()` already produces a
`VerificationReport` (max bound/row/integrality violation, objective
reconstruction delta, `passed`) that this work consumes rather than
recomputes. The `ReasonCode` enum (all 24 codes from §18.3) already exists in
`domain/enums.py` — this spec derives *which* codes apply per route, not the
vocabulary itself.

`specs/spec002/TRACEABILITY.md` carries six rows against this gap, all
`SPECIFIED` not `IMPLEMENTED`: `LP-007`, `LP-008`, `VER-001` (partially —
T10 covers the independent-check half only), `VER-002`, `VER-005`, `VER-006`.
`docs/handoff.md` names this as the concrete next task (T11) and the first
gap this repo's spec-driven scaffold should close, per its own "How to
actually start" section.

Per `agents/README.md`'s routing table, this spec was shaped using
`agents/optimization/problem_formulation/` (turning §18's prose into
REQ/AC/RISK rows) and `agents/optimization/solver_diagnostics_sensitivity/`
(shadow-price and reason-code correctness); `agents/workflow_orchestrator/`
governs the stage gate this spec must clear before `plan.md`/`tasks.md` are
acted on.

## Goals

- Assemble a complete `OptimizationResult` populating all fifteen §18.1
  sections from a `CompiledProblem`, a `SolverResult`, and a
  `VerificationReport` — no section left as a stub.
- Reconstruct each objective component's unscaled USD value from domain
  allocations and reconcile the sum to the solver's claimed objective within
  the verifier's existing tolerance (§18.2).
- Derive `ReasonCode` explanations per material route change from
  coefficients, bounds, slacks, and allocation deltas — deterministically,
  with no dependency on generated prose for correctness (§18.3).
- Report LP shadow prices (row duals) when the backend supplies them and
  verification passes, labeled with objective scale and sign convention, and
  never surfaced for MIP results (§18.4).
- Close `LP-007`, `LP-008`, `VER-001`, `VER-002`, `VER-005`, `VER-006` in
  `specs/spec002/TRACEABILITY.md` from `SPECIFIED` to `IMPLEMENTED`.

## Non-Goals

- The public API / CLI facade (`InventoryOptimizer`, `load_config`,
  `inventory-optimizer` console scripts) — that is T12, its own spec.
- Infeasibility diagnostics and repair-mode reporting (§19) — a later,
  separate task; this spec only reports results for solves that returned a
  primal.
- A MIP-local-sensitivity re-solve (§18.4's optional "re-solve a fixed-integer
  LP for local sensitivity") — no MIP business rules exist yet (Phase 3);
  tracked as a follow-up once T-series MIP work lands.
- Natural-language rendering of reason codes into prose — §18.3 explicitly
  requires correctness to not depend on prose; a renderer may consume the
  structured `ReasonCode` output later, but is not this spec's job.
- Collateral, desk, and source economics beyond what the currently-implemented
  components (`fee_revenue`, `transition_cost`) and baseline domain contracts
  already produce — sections without an upstream data source yet (e.g.
  reinvestment, collateral haircut/margin) are populated as empty/`None` per
  their §18.1 contents, not fabricated.

## Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| REQ-001 | The system shall define `VerifiedSolution` and `ObjectiveAttribution` types (named in `components/interfaces.py` but not yet introduced) and implement `attribute()` on every registered objective component (`fee_revenue`, `transition_cost`) against them. | must |
| REQ-002 | The system shall sum every objective component's attributed unscaled USD value and reconcile it to `SolverResult.objective_value_unscaled` within the verifier's tolerance, raising a structured error (not a silent rounding) on mismatch. | must |
| REQ-003 | The system shall assemble a complete `OptimizationResult` covering all fifteen §18.1 sections (Identity, Status, Allocations, Balances, Economics, Demand, Schedules, Collateral, Desk, Sources, Constraints, Solver, Verification, Warnings, Platform) from `CompiledProblem` + `SolverResult` + `VerificationReport` + the originating request/domain objects. | must |
| REQ-004 | The system shall derive `ReasonCode` explanations per route with a material allocation change, from coefficients, bounds, slacks, reduced costs, and allocation deltas — never from an LLM or free-text generation step. | must |
| REQ-005 | The system shall report row-level shadow prices from `SolverResult.dual` when non-`None` and `VerificationReport.passed` is true, labeled with the objective's scale and sign convention, mapped back to named constraint rows via `RowIndex`. | must |
| REQ-006 | The system shall omit shadow prices (not report a stale or misleading value) whenever `SolverResult.dual` is `None` — which the HiGHS backend already guarantees whenever integer variables are present. | must |

## Non-Functional Requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | Reconciliation tolerance | Objective attribution delta uses the same tolerance as `validation/solution_verifier.py::DEFAULT_TOLERANCE` (1e-6) so `VER-002` and `VER-001`/`VER-006` cannot silently disagree. |
| NFR-002 | No solver-model leakage | `OptimizationResult` never embeds the raw `CompiledProblem` (sparse matrices, raw coefficient arrays) — §20.1's "never serialize a solver model by default" applies to the reporting layer too. |
| NFR-003 | Vectorized assembly | Result/attribution/explanation assembly does not iterate route-by-route in a dataframe loop for the hot path (routes, balances); §20.1's vectorization requirement extends to reporting, not only formulation. |
| NFR-004 | Determinism | Given the same `CompiledProblem`/`SolverResult`/`VerificationReport` triple, result assembly is a pure function — identical output on every call, no wall-clock or random state read. |

## Acceptance Criteria

| ID | Given / When / Then | Covers |
| --- | --- | --- |
| AC-001 | Given a solved small/golden LP fixture, when `attribute_objective()` runs, then every registered objective component returns a finite unscaled USD value and no component raises `NotImplementedError`. | REQ-001 |
| AC-002 | Given the same fixture, when attributed component values are summed, then the sum matches `SolverResult.objective_value_unscaled` within `DEFAULT_TOLERANCE`. | REQ-002, NFR-001 |
| AC-003 | Given a fixture engineered so a component's `contribute()` and `attribute()` coefficients disagree (a seeded bug), when attribution runs, then a structured `AttributionMismatchError` (or equivalent) is raised rather than a result being returned. | REQ-002 |
| AC-004 | Given a solved golden fixture, when `build_optimization_result()` runs, then every one of the fifteen §18.1 sections is present on the returned `OptimizationResult` and none raises `NotImplementedError`. | REQ-003 |
| AC-005 | Given a route whose allocation increases because its net fee coefficient is highest among eligible routes, when explanations are derived, then `ReasonCode.HIGHER_NET_FEE` is present for that route with evidence citing the coefficient comparison. | REQ-004 |
| AC-006 | Given a route bound by a binding demand-cap row (zero slack, at upper bound), when explanations are derived, then `ReasonCode.DEMAND_CAP_BINDING` is present for that route. | REQ-004 |
| AC-007 | Given a route with no material allocation delta, when explanations are derived, then no reason codes are attached (explanations are only produced for material changes, not every route). | REQ-004 |
| AC-008 | Given a solved continuous-LP golden fixture with `SolverResult.dual` populated and verification passed, when shadow prices are built, then every binding row has a labeled dual value traceable via `RowIndex` to its domain constraint. | REQ-005 |
| AC-009 | Given a solved fixture with integer variables present (`SolverResult.dual is None`), when shadow prices are built, then the result's shadow-price section is empty/`None`, never a stale or fabricated value. | REQ-006 |
| AC-010 | Given AC-001 through AC-009 pass, when `specs/spec002/TRACEABILITY.md` is updated, then `LP-007`, `LP-008`, `VER-001`, `VER-002`, `VER-005`, `VER-006` read `IMPLEMENTED` with an evidence pointer to the tests above. | REQ-001-REQ-006 |

## Data & Dependencies

- `formulation.compiled.CompiledProblem` (T08), `ports.solver.SolverResult`
  (T09/T09 HiGHS backend), `validation.solution_verifier.VerificationReport`
  (T10) — all already implemented, read-only inputs to this work.
- `domain.enums.ReasonCode` (already implemented) — the fixed vocabulary this
  spec derives membership against; not modified here.
- `components.registry` / `components.decorators` — used to enumerate
  registered objective components at attribution time; no registry changes.
- `tests/golden/` fixtures (existing small/golden LP scenarios used by T01-T10)
  — reused rather than duplicated for this spec's AC evidence.
- No external data source, market data, or private/client data is introduced.

## Risks

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| RISK-001 | An objective-attribution bug reconciles by coincidence (compensating errors in two components) and passes a loose tolerance check. | A silently wrong economics breakdown reaches a desk user with a false "verified" label. | Tolerance matches the independent verifier's own (`DEFAULT_TOLERANCE`, already proven tight enough for T10); AC-003 requires a seeded-mismatch fixture to prove the check actually fails closed, not just that it passes on well-behaved input. |
| RISK-002 | Shadow prices computed for a MIP (or a repaired/relaxed) solve are presented as valid marginal economics. | A trader or the desk misreads a locally-invalid dual as a tradeable marginal fee/cost signal. | REQ-006 hard-omits shadow prices whenever `dual is None` (already guaranteed by the HiGHS backend for integer solves); labeling explicitly states LP-only scope per §18.4; no MIP re-solve path is built until Phase 3 requires it (non-goal). |
| RISK-003 | Reason-code derivation produces false positives/negatives that erode trust in explanations faster than no explanation would. | Desk users stop trusting or start over-trusting automated reasons. | AC-005/006/007 pin down both a positive case (code fires) and a negative case (no code on an immaterial change); `solver_diagnostics_sensitivity` agent review is the required design gate before this row is marked done. |

## Assumptions & Open Questions

- Assumption: "material" route change (§18.3's trigger for producing reason
  codes at all) is defined the same way `VerificationReport`'s reconstruction
  tolerance already treats near-zero deltas — i.e. changes below
  `DEFAULT_TOLERANCE` are not "material." `plan.md` should confirm this
  explicitly rather than inventing a second threshold.
- Open question: whether `OptimizationResult`'s currently-empty sections
  (Collateral, Schedules, Sources, Desk) should be typed as `None` or as
  empty-but-present nested models when their upstream data doesn't exist yet.
  `plan.md` decides; either choice must keep `extra="forbid"` on the frozen
  model.
- Open question: exact exception type/name for AC-003's mismatch case
  (`AttributionMismatchError` is a placeholder name here) — `plan.md`/`tasks.md`
  fix it.

## Exceptions

None recorded.
