# Tasks: Deterministic multi-period settlement (Phase 5 item 2, deterministic form)

- **Spec:** 0010-multi-period-settlement (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-07

> Ordered, testable units of work. Every task cites the requirement(s) it advances
> and carries a Definition of Done. No task without a requirement.

**Status note:** drafted 2026-09-07, **not approved**. `spec.md` carries three open design
questions (see its Open Questions) that need owner sign-off *before T-001 starts* — the same gate
`specs/0009-discrete-fee-tier-pricing/` went through: drafted, then approved once its own three
blocking questions were resolved. All tasks are `todo`; none of this spec is built yet.

## Definition of Done (applies to every task)

- Code matches `plan.md`; deviations noted there before merge, not silently.
- Tests exist and pass deterministically (`pytest tests/ -q`).
- Reproducibility preserved (no wall-clock/random state; every `planning_periods` date treated as
  a valid settlement day, per the documented calendar simplification).
- No secrets, credentials, or private data introduced.
- Every existing test continues to pass unchanged (NFR-001), and `apply_scenario`'s own existing
  tests keep passing unchanged through the `select_effective_events`/`apply_events` extraction
  (RISK-004) — this is checked *before* any new `settlement/` code is added, not after.
- No compiler (`formulation/`, `components/`, `solvers/`) changes at all (REQ-008).
- `specs/spec002/TRACEABILITY.md` (new `MPS-001`/`MPS-002` rows) and `docs/handoff.md` are updated
  alongside the change that closes them (T-011, T-012).

## Task List

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-001 | Add `OptimizationRequest.planning_periods`/`.known_future_events` with validators (strictly increasing periods, all after `effective_date`; reject non-empty events with empty periods). | REQ-001, REQ-002 | todo | Optional and empty by default; an unset request is byte-identical to today's. |
| T-002 | Refactor `scenarios/apply.py`: extract `select_effective_events`/`apply_events` from `apply_scenario`'s inline logic; confirm `apply_scenario`'s own existing tests still pass unchanged. | REQ-003 | todo | Do this **before** T-003 — it is the acceptance bar for reuse safety (RISK-004), not a detail to verify after the fact. |
| T-003 | Add `settlement/__init__.py`, `settlement/project.py::project_multi_period` (period-zero settling, per-period event application via T-002's helpers, `PeriodBalance`/`PeriodEconomics` construction, `disclosure`). | REQ-003, REQ-004, REQ-005, REQ-009 | todo | Pure function; no I/O, no compiler dependency. |
| T-004 | Add `domain/settlement.py::PeriodBalance`, `PeriodEconomics`, `MultiPeriodProjection`; add `config/models.py::MultiPeriodConfig` (`daily_discount_rate`, default `0.0`) and wire it into `InventoryOptimizerConfig`. | REQ-006, REQ-007 | todo | Additive-only; a config predating this field behaves identically. |
| T-005 | Wire `fee_revenue_coefficient` reuse into `PeriodEconomics`'s undiscounted-revenue computation, plus the discount-factor formula. | REQ-006 | todo | No new coefficient formula — reuse, not re-derivation. |
| T-006 | Add an architecture-boundary test proving `settlement/` imports nothing from `formulation/`, `components/`, or `solvers/`. | REQ-008 | todo | Mirrors `tests/unit/test_architecture_boundaries.py`'s existing `adapters/` check (`specs/0008-tabular-result-output/`). |
| T-007 | Tests: `tests/golden/test_multi_period_settlement.py`, `tests/unit/test_settlement_project.py`, `tests/unit/test_domain_contracts.py` additions. Confirm all pre-existing tests still pass (AC-001). | REQ-001 through REQ-010, NFR-001 through NFR-004 | todo | See Test Coverage Map and `plan.md`'s worked fixture sketch. |
| T-008 | Add a `slow`-marked scale test if `project_multi_period`'s per-period `apply_events` cost is material at realistic period counts — otherwise record why it was not needed. | NFR-001 | todo | Judgment call at implementation time; each period's cost is `O(routes + inventory)`, materially cheaper than `specs/0009`'s `J*K` growth, so this may turn out unnecessary. |
| T-009 | Facade/service wiring: a `SettlementService`-shaped explicit entry point (mirroring `ScenarioService`), **not** auto-invoked from `InventoryOptimizer.optimize()`. | REQ-008 | todo | Explicit call only, matching `run_stress_test`'s own precedent (library function first, no CLI yet). |
| T-011 | Add `specs/spec002/TRACEABILITY.md` rows `MPS-001` (deterministic multi-period balance projection, §22.11) and `MPS-002` (formulation-independence). | REQ-001 through REQ-010 | todo | New prefix — no existing row covers §22.11/§22.12 today. |
| T-012 | Update `docs/handoff.md` and `specs/README.md`: record this spec, and restate that §22.12's stochastic/scenario-tree extension and Design A (the full joint multi-period LP) remain open/deferred. | REQ-001 through REQ-010 | todo | Phase 5 item 2 is *not* complete when this ships — only its deterministic-projection form. |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | Full suite rerun; no test targets this directly since nothing changes for an unset request | todo |
| AC-002 | `test_domain_contracts.py::test_optimization_request_rejects_known_future_events_without_periods` | todo |
| AC-003 | `test_multi_period_settlement.py::test_recall_lands_in_its_own_period_not_earlier` | todo |
| AC-004 | `test_multi_period_settlement.py::test_period_economics_matches_hand_formula` | todo |
| AC-005 | `test_multi_period_settlement.py::test_invariant_violation_raises_not_silently_clipped` | todo |
| AC-006 | `test_settlement_project.py::test_projection_is_formulation_independent` | todo |
| AC-007 | `test_settlement_project.py::test_disclosure_is_always_present` | todo |

## Follow-ups

Tracked work intentionally deferred (no silent "temporary" shortcuts — P8).

- **Design A — the full joint multi-period LP** — time-indexed decision variables across every
  route and period, jointly optimized. This spec deliberately builds the smaller, deterministic
  projection instead; nothing here forecloses it, and the two designs may or may not end up sharing
  `planning_periods`/`known_future_events` as a common input shape (spec.md's own open question).
- **§22.12's stochastic/scenario-tree extension** — probability-weighted scenarios, CVaR, chance
  constraints. Entirely untouched.
- **`LoanRoute.recall_notice_days` validation against a known future `RECALL` event's timing** —
  deferred pending owner sign-off (spec.md's Open Questions).
- **A real business-day/holiday calendar** — every `planning_periods` date is a valid settlement
  day for V1. No calendar port exists anywhere in this repo yet.
- **Corporate-action deltas / cross-currency effects on projected lendable quantity** — fixed at
  zero; no corporate-action domain model exists yet.
- **A CLI subcommand** — library function only, matching `run_stress_test`'s own precedent.
- **A `reporting/tables.py` settlement table builder**, mirroring the existing scenario/stress
  table builders — not required for this spec's own ACs; a natural follow-on once
  `specs/0008-tabular-result-output/`'s table catalogue is extended.
