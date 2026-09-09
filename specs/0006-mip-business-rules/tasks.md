# Tasks: MIP business rules (Phase 3)

- **Spec:** 0006-mip-business-rules (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-05

> Ordered, testable units of work. Every task cites the requirement(s) it advances
> and carries a Definition of Done. No task without a requirement.

**Status note:** all nine tasks below are `done`. Phase 3 is implemented, tested, and traced.

## Definition of Done (applies to every task)

- Code matches `plan.md`; deviations noted there before merge, not silently.
- Tests exist and pass deterministically (`pytest tests/ -q`).
- Reproducibility preserved (no wall-clock/random state in any new compiler code).
- No secrets, credentials, or private data introduced.
- Every existing test continues to pass unchanged (NFR-001) — this is the one spec in this repo
  so far whose core requirement is *not* breaking anything already implemented.
- `specs/engine_spec/TRACEABILITY.md`'s `LP-009` row and `docs/handoff.md`'s "Next priorities" section
  are updated alongside the change that closes them (T-008, T-009).

## Task List

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-001 | Add `formulation/compiler_support.py`: `resolve_component`, `set_route_bounds` (moved from `formulation/lp.py`, made public), `needs_mip`, `mip_required_issues`. | REQ-006, NFR-002 | done | Same-behavior move for the first two, matching T12's `build_context` extraction precedent. |
| T-002 | Extend `formulation/context.py::build_context`: compute `activation_route_ids`/`lot_size_route_ids`, add `z`/`n` variable blocks (empty when unused). Add `domain/policies.py::UtilizationPolicy.maximum_active_routes`. | REQ-004, NFR-001 | done | Confirmed via the existing E1/E2/E3 tests: empty blocks contribute zero positions, so `q`/`inc`/`dec`/`a` never shift. |
| T-003 | Add `components/constraints/mip_rules.py`: `RouteActivationConstraint`, `CardinalityConstraint`, `LotSizeConstraint`. | REQ-001, REQ-002, REQ-003, REQ-004 | done | `CardinalityConstraint` imports `_policy_applies` directly from `components/constraints/utilization.py` (sibling-module reuse, not a cross-layer reach-in). |
| T-004 | Add `formulation/mip.py::compile_mip`, `MIP_CONSTRAINTS`. | REQ-005 | done | Imports `REQUIRED_CONSTRAINTS`/`REQUIRED_OBJECTIVES` from `formulation.lp` (one-directional; also triggers the baseline components' registration as an import side effect). |
| T-005 | Update `formulation/lp.py::compile_lp`: import `resolve_component`/`set_route_bounds` from `compiler_support` (remove the local private copies); raise via `needs_mip`/`mip_required_issues` before compiling. | REQ-006 | done | The one deliberate behavior change in this spec (RISK-001) — every other line of `compile_lp` is unchanged. |
| T-006 | Update `facade.py::InventoryOptimizer.optimize`: route to `compile_mip` when `needs_mip(request)`, else `compile_lp`. | REQ-007 | done | No new public parameter. |
| T-007 | Tests: `tests/golden/test_mip_business_rules.py` (AC-001 through AC-004, AC-008, AC-009); `tests/unit/test_mip_compiler.py` (AC-006, `compile_mip` row/variable shape per trigger, `needs_mip`). Confirm all pre-existing tests still pass (AC-005). | REQ-001 through REQ-009, NFR-001, NFR-003 | done | See Test Coverage Map below. |
| T-008 | Update `specs/engine_spec/TRACEABILITY.md`'s `LP-009` row: evidence pointer to this spec's tests; status becomes `IMPLEMENTED` for the MIP portion only (QP/PWL/NLP explicitly still `SPECIFIED`, tagged `T18` and later). | REQ-001 through REQ-009 | done | Mirrors T11/T12's own partial-implementation honesty precedent (`LP-008`, `PLT-002`). |
| T-009 | Update `docs/handoff.md`: mark Phase 3 (this spec) done; identify the next task (Phase 4, QP, per `00_PLAN.md`). | REQ-001 through REQ-009 | done | |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | `test_mip_business_rules.py::test_all_or_none_never_partially_fills`, `::test_all_or_none_can_choose_zero_when_uneconomic` | done |
| AC-002 | `test_mip_business_rules.py::test_minimum_ticket_never_partially_activates` | done |
| AC-003 | `test_mip_business_rules.py::test_lot_size_quantity_is_exact_multiple` | done |
| AC-004 | `test_mip_business_rules.py::test_cardinality_limits_active_routes` | done |
| AC-005 | Existing `test_e1_scarce_name_allocation.py`, `test_e2_fee_elasticity_shock.py`, `test_e3_sale_and_recall_scenario.py`, `test_lp_compiler.py`, and every other pre-existing test all still pass unchanged (172 total, 0 regressions) | done |
| AC-006 | `test_mip_compiler.py::test_compile_lp_rejects_each_mip_trigger` (parametrized: `all_or_none`, `lot_size_shares`, `minimum_active_quantity_shares`), `::test_compile_lp_rejects_cardinality_policy` | done |
| AC-007 | `test_mip_business_rules.py::test_all_or_none_never_partially_fills` (same solve, via the facade) | done |
| AC-008 | `test_mip_business_rules.py::test_integrality_violation_caught_on_real_mip` | done |
| AC-009 | `test_mip_business_rules.py::test_no_shadow_prices_for_real_mip_solve` | done |

## Follow-ups

Tracked work intentionally deferred (no silent "temporary" shortcuts — P8).

- Fixed route activation cost, discrete rate-ladder selection, and a richer mutual-exclusion
  concept wait on a new domain field/worked example — see `spec.md` Non-Goals.
- A friendlier diagnostic for combining `lot_size_shares` with `all_or_none`/`minimum_active_
  quantity_shares` on the same route when the numbers don't divide evenly (RISK-003) is untracked
  by any task yet.
- MIP-scale performance benchmarking (a cardinality policy scoped broadly could add many binary
  variables, RISK-002) waits on extending `specs/0005-test-hardening/`'s Core-desk benchmark to a
  MIP variant.
- `01_SPEC.md` §14.2-§14.4 (QP, piecewise-linear, nonlinear) are `00_PLAN.md`'s Phase 4-5, not
  started.
