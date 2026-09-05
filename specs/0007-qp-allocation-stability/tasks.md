# Tasks: QP allocation-stability penalty (Phase 4)

- **Spec:** 0007-qp-allocation-stability (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-05

> Ordered, testable units of work. Every task cites the requirement(s) it advances
> and carries a Definition of Done. No task without a requirement.

**Status note:** all nine tasks below are `done`. Phase 4's allocation-stability term is
implemented, tested, and traced.

## Definition of Done (applies to every task)

- Code matches `plan.md`; deviations noted there before merge, not silently.
- Tests exist and pass deterministically (`pytest tests/ -q`).
- Reproducibility preserved (no wall-clock/random state in any new compiler code).
- No secrets, credentials, or private data introduced.
- Every existing test continues to pass unchanged (NFR-001) — this spec's core promise, same as
  `0006`'s before it.
- `specs/spec002/TRACEABILITY.md`'s `LP-009` row and `docs/handoff.md`'s "Next priorities" section
  are updated alongside the change that closes them (T-010, T-011).

## Task List

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-001 | Add `config/models.py::ObjectiveConfig` (`allocation_stability_penalty`, default `0.0`); wire into `InventoryOptimizerConfig`, `config/__init__.py`, `configs/default.yaml`. | REQ-001 | done | Closes Section 8.2's own "objective section added when that subsystem lands" note. |
| T-002 | Add `components/objective_terms/allocation_stability.py::AllocationStabilityPenalty`. | REQ-001 | done | Registered `formulations={Formulation.QP}` only, unlike the baseline components' `{LP, MIP, QP}`. |
| T-003 | Add `formulation/qp_support.py` (`signed_hessian`, `signed_quadratic_term`, `validate_psd`); extend `formulation/compiler_support.py::resolve_component` with a required `formulation=` keyword and membership check. | REQ-002, REQ-010 | done | Verified every existing component's declared `formulations` set is already correct/complete before relying on the new check. |
| T-004 | Add `formulation/qp.py::compile_qp`, `QP_OBJECTIVES`, `_objective_scaling`; extend `sparse_builder.py` with `add_quadratic_objective_coefficient` and internal `quadratic_objective` accumulation (removing the previously-unused external parameter). | REQ-002, REQ-008 | done | PSD validation and scaling both applied only when a quadratic term actually exists. |
| T-005 | Extend `formulation/compiler_support.py` with `needs_qp`, `qp_required_issues`, `miqp_conflict_issues`; update `formulation/lp.py::compile_lp` (aggregate both rejection sources) and `formulation/mip.py::compile_mip` (new MIQP pre-flight check). | REQ-003, REQ-004 | done | The one deliberate behavior change in this spec, mirroring `0006`'s RISK-001 precedent. |
| T-006 | Update `facade.py::InventoryOptimizer.optimize`: route to `compile_qp` when `needs_qp(config)` (after the existing `needs_mip` check). | REQ-005 | done | No new public parameter. |
| T-007 | Update `solvers/highs.py`: `HighsBackend` gains `Capability.CONTINUOUS_QP`; `_build_highs_lp`/new `_build_highs_hessian` accept a scale factor read from `problem.scaling`; `solve()` divides the solved objective and duals back down by the same factor. | REQ-006, REQ-008 | done | Empirically confirmed against the pinned `highspy` version (see `plan.md`'s scaling account) before finalizing. |
| T-008 | Update `validation/solution_verifier.py`: objective reconstruction includes the sense-signed quadratic term via `formulation.qp_support.signed_quadratic_term`. | REQ-007 | done | No other change; still compares against `objective_value_unscaled` exactly as before. |
| T-009 | Tests: `tests/golden/test_qp_allocation_stability.py` (AC-001 through AC-003, AC-007, AC-008); `tests/unit/test_qp_compiler.py` (AC-004, AC-005, `compile_qp` row/scaling shape, `needs_qp`); `tests/unit/test_qp_support.py` (AC-006); `tests/benchmark/test_qp_scale.py` (AC-010, `slow`-marked). Confirm all pre-existing tests still pass (AC-009). | REQ-001 through REQ-010, NFR-001 through NFR-003 | done | See Test Coverage Map below. |
| T-010 | Update `specs/spec002/TRACEABILITY.md`'s `LP-009` row: extend the evidence pointer to this spec's tests; note remains `IMPLEMENTED` (MIP + QP allocation-stability portions; PWL/NLP explicitly still `SPECIFIED`, tagged `T18` and later). | REQ-001 through REQ-010 | done | Extends, not replaces, `0006`'s own evidence entry. |
| T-011 | Update `docs/handoff.md`: mark Phase 4 (this spec) done; identify the next task (Phase 5, nonlinear/multi-period research, per `00_PLAN.md`). | REQ-001 through REQ-010 | done | |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | `test_qp_allocation_stability.py::test_zero_penalty_matches_lp_behavior` | done |
| AC-002 | `test_qp_allocation_stability.py::test_moderate_penalty_pulls_toward_current_book` | done |
| AC-003 | `test_qp_allocation_stability.py::test_large_penalty_holds_near_current_book` | done |
| AC-004 | `test_qp_compiler.py::test_compile_lp_rejects_positive_penalty` | done |
| AC-005 | `test_qp_compiler.py::test_compile_mip_rejects_qp_conflict`, `::test_compile_qp_rejects_mip_conflict` | done |
| AC-006 | `test_qp_support.py::test_validate_psd_accepts_psd_matrix`, `::test_validate_psd_rejects_indefinite_matrix`, `::test_validate_psd_sparse_path_rejects_indefinite_block` | done |
| AC-007 | `test_qp_allocation_stability.py::test_attribution_reconciles_and_matches_hand_formula` | done |
| AC-008 | `test_qp_allocation_stability.py::test_shadow_prices_are_populated_and_correctly_scaled` | done |
| AC-009 | Existing `test_e1_scarce_name_allocation.py`, `test_lp_compiler.py`, `test_mip_compiler.py`, and every other pre-existing test all still pass unchanged (172 total, 0 regressions) | done |
| AC-010 | `test_qp_scale.py::test_qp_compile_and_solve_completes_within_time_ceiling` | done |

## Follow-ups

Tracked work intentionally deferred (no silent "temporary" shortcuts — P8).

- Borrower/security concentration penalty, covariance-weighted revenue/recall risk, and smooth
  utilization-target deviations (§14.2's other three candidate terms) each wait on a new domain
  concept with no grounding yet — see `spec.md` Non-Goals.
- Mixed-integer QP (combining Phase 3's MIP triggers with this spec's penalty) waits on a separate
  capable backend or an explicitly documented decomposition (Section 14.2) — untracked by any task
  beyond the fail-closed rejection this spec already builds.
- Whether the scaling rule generalizes correctly once a second QP objective term exists is an open
  question (`spec.md`) with no task yet.
- `01_SPEC.md` §14.3-§14.4 (piecewise-linear, nonlinear) are `00_PLAN.md`'s Phase 5, not started.
