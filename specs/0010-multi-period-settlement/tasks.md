# Tasks: Multi-period settlement — deterministic projection and joint LP (Phase 5 item 2)

- **Spec:** 0010-multi-period-settlement (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-09

> Ordered, testable units of work. Every task cites the requirement(s) it advances
> and carries a Definition of Done. No task without a requirement.

**Status note:** approved 2026-09-07 (owner: build both designs, sequenced; validate recall
notice; discount rate configurable, defaulting to zero). **Phase 1 (T-001 through T-006) is
`done`** — the shared fields, recall-notice validation, and the deterministic projection, a
complete, independently useful increment: 15 new tests (254 total, zero regressions in the
pre-existing 239), including `apply_scenario`'s own 13 existing tests passing unchanged through
the `select_effective_events`/`apply_events` extraction. **T-007 is also `done`** (merged to
`main` alongside a Phase 1 fix — see its own row's Notes); this row was left `todo` at merge time
and is corrected here (2026-09-09), a doc-sync gap, not a functional one — the code and its tests
were already present and passing. **T-008 is also `done`** (2026-09-09, on branch
`0010-t008-multi-period-lp-rows`) — the new `formulation/multi_period.py`'s period-indexed row-
building functions and `_period_bound_adjustments`; see its own row's Notes. **T-009 is also
`done`** (2026-09-09, same branch) — `components/objective_terms/multi_period_economics.py`; see
its own row's Notes. **Phase 2's remaining tasks (T-010 through T-014, the joint multi-period LP's
compiler entry point, tests, and traceability/handoff sync) are `todo` — resume there.**

## Definition of Done (applies to every task)

- Code matches `plan.md`; deviations noted there before merge, not silently.
- Tests exist and pass deterministically (`pytest tests/ -q`).
- Reproducibility preserved (no wall-clock/random state; every `planning_periods` date treated as
  a valid settlement day, per the documented calendar simplification).
- No secrets, credentials, or private data introduced.
- `apply_scenario`'s own existing tests keep passing unchanged through the
  `select_effective_events`/`apply_events` extraction (RISK-003) — checked *before* any new
  `settlement/`/`formulation/multi_period.py` code is added.
- Every existing test continues to pass unchanged (NFR-001).
- Phase 2 introduces no compiler change to `formulation/lp.py`, `formulation/mip.py`, or
  `formulation/qp.py` themselves — only a new, separate compiler plus one new `facade.py` branch
  and one new `compiler_support.py` predicate pair.
- `specs/engine_spec/TRACEABILITY.md` (new `MPS-001`/`MPS-002`/`MPS-003` rows) and `docs/handoff.md`
  are updated alongside the change that closes them (T-013, T-014).

## Task List

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-001 | Add `OptimizationRequest.planning_periods`/`.known_future_events` with validators (strictly increasing periods, all after `effective_date`; reject non-empty events with empty periods). | REQ-001, REQ-002 | done | Optional and empty by default; an unset request is byte-identical to today's. |
| T-002 | Add `validation/reconciliation.py::check_recall_notice_sufficiency`; wire into `reconcile()`. | REQ-003 | done | Notice measured `effective_date - trade_date` against the route's own `recall_notice_days`, not against `request.effective_date`. |
| T-003 | Refactor `scenarios/apply.py`: extract `select_effective_events`/`apply_events` from `apply_scenario`'s inline logic; confirm `apply_scenario`'s own existing tests still pass unchanged. | REQ-004 | done | All 13 pre-existing `test_scenarios_apply.py` tests pass unchanged. |
| T-004 | Add `settlement/__init__.py`, `settlement/project.py::project_multi_period` (period-zero settling, per-period event application via T-003's helpers, `PeriodBalance` construction, `mode="projected"`). | REQ-004, REQ-005, REQ-006 | done | Pure function; no compiler dependency. |
| T-005 | Add `domain/settlement.py::PeriodBalance`, `PeriodEconomics`, `MultiPeriodProjection` (with `mode`/`disclosure`); add `config/models.py::MultiPeriodConfig` (`daily_discount_rate`, default `0.0`) and wire into `InventoryOptimizerConfig`; wire `fee_revenue_coefficient` reuse + discount factor into `PeriodEconomics`. | REQ-007, REQ-008 | done | Also promoted `fee_revenue.py`'s `DAY_COUNT_DIVISOR` from private to shared (one source of truth for `act_360`/`act_365`), reused here with a period-specific day count instead of `planning_horizon_days`. |
| T-006 | Phase 1 tests: `tests/golden/test_multi_period_settlement.py`, `tests/unit/test_settlement_project.py`, `tests/unit/test_domain_contracts.py`/`test_validation.py` additions. Confirm all pre-existing tests still pass. | REQ-001 through REQ-008, NFR-001 through NFR-004 | done | 15 new tests; 254 passed, 2 skipped, zero regressions in the pre-existing 239. |
| T-007 | Add `formulation/compiler_support.py::needs_multi_period`/`multi_period_conflict_issues` (fails closed on MIP/QP/fee-tier combination). | REQ-012 | done | Mirrors `needs_mip`/`needs_qp`'s existing pattern; **no `facade.py` change** — `optimize()` must keep ignoring `planning_periods` since Phase 1 depends on that (plan.md's corrected "separate entry point" section). Status corrected 2026-09-09 — code was committed and merged but this row was left `todo`. Its own dedicated test (AC-007) is still pending under T-011, the same sequencing T-001–T-005 used ahead of T-006. |
| T-008 | Inside `formulation/multi_period.py`: period-indexed row-building functions for `inventory_balance`/`transition_identity`/`demand_cap`/`utilization_cap`/`reserve_buffer`/`counterparty_limit`, plus the `_period_bound_adjustments` helper (Phase 2's own, distinct-from-`apply_events`, bound-tightening logic). | REQ-009, REQ-010 | done | Plain functions (`MultiPeriodContext`/`RouteGroupings`/`PeriodBounds` dataclasses, not registered components) mirroring each baseline formula against `period_scope_id`-suffixed `VariableKey`s; period 0's `transition_identity` row is byte-identical to today's baseline (verified manually -- lower=upper=`current_quantity_shares`, no `q_{t-1}` term). `formulation.context._group_by` promoted to public `group_by` (docs/handoff.md's resume note); RETURN's bound-formula reading (identical to RECALL's `max(maximum_quantity_shares - qty, hard_minimum_quantity_shares)`) recorded in plan.md before implementation (constitution P8). Not yet wired into a compiler entry point (T-010) or exercised by a dedicated test (T-011, per this file's own sequencing note); full pre-existing suite (255 passed, 2 skipped) unchanged. |
| T-009 | Add `components/objective_terms/multi_period_economics.py` (discounted per-period fee revenue + transition cost, generalized day-count fraction per period). | REQ-007, REQ-011 | done | Plain function `multi_period_economics(context: MultiPeriodContext, builder)`, mirroring `formulation/multi_period.py`'s own six row-building functions' shape; `MultiPeriodContext` (T-008) gained `day_count_fraction`/`discount_factor` fields for it to read. `fee_revenue.py` refactored to extract `fee_revenue_coefficient_for_tau` (tau as a direct parameter) with `fee_revenue_coefficient` now a thin wrapper over it -- literal code reuse, not just formula reuse; existing tests confirm the wrapper's behavior is unchanged. `period_economics_factors(boundaries, config)` generalizes T08's single-period `tau`/computes `discount_factor_t` per `plan.md`'s Objective section, mirroring (not sharing code with) `settlement/project.py`'s Phase 1 per-period economics construction. Verified via a scratch fixture (not a committed test -- T-011's job): period 0's coefficients match the single-period baseline exactly, later periods' `day_count_fraction` is the gap from the previous boundary, and `discount_factor` decreases correctly under a positive `daily_discount_rate`. Full pre-existing suite (255 passed, 2 skipped) unchanged. |
| T-010 | Add `formulation/multi_period.py::compile_multi_period_lp` tying T-007 through T-009 together, plus `solve_multi_period` (the new, separate entry point: validate + compile + solve + verify + `mode="jointly_optimized"` result construction, reusing `domain/settlement.py` from T-005). | REQ-009 through REQ-012 | todo | No changes to `solvers/highs.py`, `validation/solution_verifier.py`, or `facade.py` — the `CompiledProblem` shape is structurally an ordinary LP, and `solve_multi_period` composes the same stages `optimize()` does without touching it. |
| T-011 | Phase 2 tests: `tests/golden/test_multi_period_lp.py`, `tests/unit/test_multi_period_lp_compiler.py`. Confirm all pre-existing tests (Phase 1 included) still pass. | REQ-009 through REQ-013, NFR-001, NFR-005 | todo | See Test Coverage Map and `plan.md`'s Phase 2 worked fixture. |
| T-012 | Add a `slow`-marked scale test sizing Phase 2's route × period growth. | REQ-009 | todo | RISK-004; follows `specs/0005-test-hardening/`/`specs/0009`'s benchmark precedent. |
| T-013 | Add `specs/engine_spec/TRACEABILITY.md` rows `MPS-001` (Phase 1), `MPS-002` (Phase 2), `MPS-003` (recall-notice validation). | REQ-001 through REQ-013 | todo | New prefix — no existing row covers §22.11/§22.12 today. |
| T-014 | Update `docs/handoff.md` and `specs/README.md`: record this spec as done, and restate that §22.12's stochastic/scenario-tree extension and MIP/QP-within-multi-period remain open/deferred. | REQ-001 through REQ-013 | todo | Do only after T-001 through T-013 are all green. |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | Full suite rerun (Phase 1: LP/MIP requests with empty `planning_periods`; Phase 2 will extend to QP) | done (Phase 1) |
| AC-002 | `test_domain_contracts.py::test_optimization_request_rejects_known_future_events_without_periods` | done |
| AC-003 | `test_validation.py::test_recall_notice_insufficient_is_reported`/`test_recall_notice_sufficient_is_accepted` | done |
| AC-004 | `test_multi_period_settlement.py::test_recall_lands_in_its_own_period_not_earlier` | done |
| AC-005 | `test_multi_period_settlement.py::test_period_economics_matches_hand_formula` | done |
| AC-006 | `test_multi_period_lp.py::test_known_future_recall_reduces_period_zero_allocation` | todo (Phase 2) |
| AC-007 | `test_multi_period_lp_compiler.py::test_mip_or_qp_trigger_combined_with_planning_periods_fails_closed` | todo (Phase 2) |
| AC-008 | `test_settlement_project.py::test_mode_is_projected` (done); `test_multi_period_lp_compiler.py::test_mode_is_jointly_optimized` | partial — projected done, jointly_optimized todo (Phase 2) |

## Follow-ups

Tracked work intentionally deferred (no silent "temporary" shortcuts — P8).

- **§22.12's stochastic/scenario-tree extension** — probability-weighted scenarios, CVaR, chance
  constraints. Entirely untouched.
- **MIP/QP business rules combined with the joint multi-period LP** — deferred (REQ-012's current
  exclusion); no desk need identified yet.
- **A real business-day/holiday calendar** — every `planning_periods` date is a valid settlement
  day for V1. No calendar port exists anywhere in this repo yet.
- **Corporate-action deltas / cross-currency effects** — fixed at zero; no corporate-action domain
  model exists yet.
- **Time-varying fee rates/prices within the horizon** — held constant across periods for V1.
- **A CLI subcommand** — library function only, matching `run_stress_test`'s own precedent.
- **A `reporting/tables.py` settlement table builder**, mirroring the existing scenario/stress
  table builders — not required for this spec's own ACs.
