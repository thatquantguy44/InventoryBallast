# Tasks: Result, objective attribution, and explainability (T11)

- **Spec:** 0002-result-attribution-explainability (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-04

> Ordered, testable units of work. Every task cites the requirement(s) it advances
> and carries a Definition of Done. No task without a requirement.

## Definition of Done (applies to every task)

- Code matches `plan.md`; deviations noted there before merge, not silently.
- Tests exist and pass deterministically (`pytest tests/ -q`).
- Reproducibility preserved: no wall-clock, random, or I/O read inside pure
  `reporting/` functions (NFR-004).
- No secrets, credentials, or private data introduced.
- `specs/spec002/TRACEABILITY.md` and `docs/handoff.md` updated alongside the
  change that closes them (T-010, T-011) — not deferred to a later commit.

## Task List

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-001 | Add `reporting/types.py`: `VerifiedSolution` (with `primal_at(VariableKey)`), `ObjectiveAttribution`, `RouteExplanation`, `ShadowPriceEntry`; add `AttributionMismatchError` to `exceptions.py`. | REQ-001 | done | Replaces the `object`/`object` placeholders named in `components/interfaces.py`'s docstring. `VerifiedSolution` carries `context: BuildContext` (not just `request`) so `attribute()` can recompute from the same domain fields `contribute()` used. |
| T-002 | Implement `FeeRevenueTerm.attribute()` in `components/objective_terms/fee_revenue.py` against `VerifiedSolution`, reconstructing `price_usd * tau * (fee_rate * revenue_share - variable_cost_rate) * q` per route from the primal. | REQ-001 | done | Extracted the shared formula into a public `fee_revenue_coefficient()` so `contribute()`, `attribute()`, and `reporting.explanations` all agree on one definition. |
| T-003 | Implement `TransitionCostTerm.attribute()` in `components/objective_terms/transition_cost.py` against `VerifiedSolution`, reconstructing `-(increase_cost * inc + decrease_cost * dec)` per route from the primal. | REQ-001 | done | |
| T-004 | Add `reporting/attribution.py::attribute_objective(solution: VerifiedSolution) -> tuple[ObjectiveAttribution, ...]`: enumerate `CompiledProblem.manifest` objective components, call `.attribute()`, sum, compare to `result.objective_value_unscaled` within `solution_verifier.DEFAULT_TOLERANCE`, raise `AttributionMismatchError` on mismatch. | REQ-002, NFR-001 | done | Signature takes one `VerifiedSolution` bundle rather than three separate params (deviation from the original sketch, kept consistent everywhere in `reporting/`). Fail-closed: never swallow or log-and-continue on mismatch. |
| T-005 | Extend `domain/results.py::OptimizationResult` with the thirteen remaining §18.1 section models. Keep `frozen=True, extra="forbid"`. | REQ-003, NFR-002 | done | Deviation from the original sketch: `domain/results.py` defines its own plain-data mirrors (`VerificationSection`, `ObjectiveAttributionRecord`, `RowIdentifier`) instead of embedding `VerificationReport`/`ObjectiveAttribution`/`RowKey` by reference, preserving the "domain imports nothing from formulation/validation/reporting" invariant every other `domain/*.py` module already follows. `Schedules`/`Collateral`/`Sources` are `None`; `Desk` is populated (`DeskContext` + `config.desk.enabled_components` already exist, so it does not belong on the "no upstream data" list the plan originally put it on). |
| T-006 | Add `reporting/explanations.py::explain_routes(solution: VerifiedSolution) -> tuple[RouteExplanation, ...]`: one independent predicate function per `ReasonCode`, evaluated per route whose allocation delta exceeds `DEFAULT_TOLERANCE`. | REQ-004, NFR-003 | done | Implemented 3 codes, not 2: `HIGHER_NET_FEE` (scoped to routes sharing the same *inventory*, not demand group — that is where Section 11.4's shared balance row actually creates competition; demand-group scoping produced a trivial always-true result whenever a group has only one route), `DEMAND_CAP_BINDING`, and `ELASTICITY_REDUCED_DEMAND` (free: already computed by T06's `elasticity.EvaluatedDemand.reason_code`, just carried through). Remaining 21 deferred per Follow-ups below. |
| T-007 | Add `reporting/shadow_prices.py::build_shadow_prices(solution: VerifiedSolution) -> tuple[ShadowPriceEntry, ...]`: guard on `result.dual is None or not verification.passed` returning `()`; otherwise zip `row_index.keys` against `result.dual`, label with `CompiledProblem.scaling.objective_scale_usd` and a fixed sign-convention string. | REQ-005, REQ-006, NFR-003 | done | |
| T-008 | Add `reporting/result_builder.py::build_optimization_result(solution: VerifiedSolution, *, run_id, created_at, config_hash, input_hash, platform=None) -> OptimizationResult`: orchestrate T-004/T-006/T-007 plus Allocations/Balances/Demand read directly from the request + primal. | REQ-003 | done | Identity fields this layer cannot compute itself (`run_id`, `created_at`, `config_hash`, `input_hash`, the platform envelope) are caller-supplied keyword args, keeping the function pure (NFR-004) — deviation from the original `(request, problem, result, verification)` sketch. |
| T-009 | Unit tests: `tests/unit/reporting/test_attribution.py`, `test_explanations.py`, `test_shadow_prices.py`, `test_result_builder.py`, reusing the E1 fixture; add one seeded-mismatch fixture (an isolated `Registry` with a fake objective component) for `AttributionMismatchError`, and one pinned-route fixture for the immaterial-change negative case. | REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-006 | done | 10 new tests, all passing; 107/107 total (`pytest tests/ -q`). See Test Coverage Map below. |
| T-010 | Update `specs/spec002/TRACEABILITY.md` rows `LP-007`, `VER-001`, `VER-002`, `VER-005`, `VER-006` from `SPECIFIED` to `IMPLEMENTED`, each pointing at the specific test(s) from T-009. | REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-006 | done | `LP-008` stays `SPECIFIED` (corrected from the original spec/plan, which wrongly listed it as closing here) — it needs the joint collateral mode, T32, not just T11; see `spec.md`'s Goals section. |
| T-011 | Update `docs/handoff.md`'s "Next priorities" section: mark T11 done with a pointer to this spec, promote T12 to the immediate next task. | REQ-003 | done | |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

Every acceptance criterion must be named by at least one test.

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | `test_attribution.py::test_all_components_attribute_without_error` (AC-001) | done |
| AC-002 | `test_attribution.py::test_attributed_sum_matches_solver_objective` (AC-002) | done |
| AC-003 | `test_attribution.py::test_mismatch_raises_attribution_error` (AC-003) | done |
| AC-004 | `test_result_builder.py::test_all_sections_present` (AC-004) | done |
| AC-005 | `test_explanations.py::test_higher_net_fee_reason_code` (AC-005) | done |
| AC-006 | `test_explanations.py::test_demand_cap_binding_reason_code` (AC-006) | done |
| AC-007 | `test_explanations.py::test_no_reason_codes_on_immaterial_change` (AC-007) | done |
| AC-008 | `test_shadow_prices.py::test_binding_row_duals_labeled_and_traceable` (AC-008) | done |
| AC-009 | `test_shadow_prices.py::test_mip_solve_has_no_shadow_prices` (AC-009) | done |
| AC-010 | `specs/spec002/TRACEABILITY.md` diff reviewed against the unit-test names above (AC-010) | done |

## Follow-ups

Tracked work intentionally deferred (no silent "temporary" shortcuts — P8).

- T12 (public API / CLI facade) is the next spec after this one ships;
  `build_optimization_result` is its primary dependency.
- Reason-code predicates beyond `HIGHER_NET_FEE`/`DEMAND_CAP_BINDING` land
  incrementally as their upstream constraint components (utilization,
  counterparty, eligibility, collateral, etc.) are implemented — each new
  constraint component's spec should add its own predicate rather than this
  spec front-loading 22 untestable stubs.
- MIP-local-sensitivity re-solve (§18.4's optional path) waits for Phase 3
  (mixed-integer business rules) to exist; revisit via
  `agents/optimization/mixed_integer_optimization/` and
  `solver_diagnostics_sensitivity` once that phase starts.
- Infeasibility/repair-mode reporting (§19) is out of scope here and untracked
  by any spec yet — worth a `specs/000X-*` of its own before Phase 2/3 need it.
