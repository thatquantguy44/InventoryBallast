# Tasks: Discrete fee-tier pricing (joint fee/quantity, Phase 5 item 1)

- **Spec:** 0009-discrete-fee-tier-pricing (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-05

> Ordered, testable units of work. Every task cites the requirement(s) it advances
> and carries a Definition of Done. No task without a requirement.

**Status note:** approved 2026-09-05, sequenced after `0008`. **Implementation started
2026-09-06** on branch `0009-discrete-fee-tier-pricing`: T-001 through T-006 (the domain field,
`BuildContext` plumbing, both new components, MIP-compiler wiring, and result reporting) are
`done` and manually smoke-tested end to end through `InventoryOptimizer.optimize()` against
`plan.md`'s worked `epsilon=0.5` fixture (reproduces the documented `D=70.71, rev=0.1414, tier
0.072 wins` values exactly, `verification.passed=True`, attribution reconciles with zero
mismatch). The full pre-existing suite (220 passed, 2 skipped) still passes unchanged after these
six tasks -- a first, informal NFR-001 signal, but **not yet a substitute for T-008's own tests**.
T-007 (scale test), T-008 (the golden/unit test files this spec's ACs actually cite), T-009
(`TRACEABILITY.md`), and T-010 (`docs/handoff.md`/`specs/README.md`) are still `todo` -- resume
there. No acceptance criterion is considered met until its named test in the Test Coverage Map
below exists and passes.

## Definition of Done (applies to every task)

- Code matches `plan.md`; deviations noted there before merge, not silently.
- Tests exist and pass deterministically (`pytest tests/ -q`).
- Reproducibility preserved (no wall-clock/random state; tier order follows the declared candidate
  order, zero-padded so lexicographic index order equals numeric order).
- No secrets, credentials, or private data introduced.
- Every existing test continues to pass unchanged (NFR-001), and an untiered request compiles to
  byte-identical variable/row indexes — the same guarantee `0006` held for `z`/`n`.
- The compiled problem stays a **linear** MIP (NFR-002): no bilinear term ever reaches the solver.
- `specs/spec002/TRACEABILITY.md` (`LP-004`, `LP-009`) and `docs/handoff.md` are updated alongside
  the change that closes them (T-009, T-010).

## Task List

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-001 | Add `DemandForecast.candidate_fee_rates: tuple[float, ...] = ()` with a validator requiring strictly positive, strictly increasing, duplicate-free values. | REQ-001 | done | Optional and empty by default; an untiered forecast is byte-identical to today's. Also caps a group at 1000 tiers (validated, not assumed), matching the zero-padded index's range. |
| T-002 | Extend `formulation/context.py`: compute `tiered_demand_group_ids` and `tier_caps` (one `EvaluatedDemand` per candidate fee via the unchanged `evaluate_demand_cap`), and append the empty-when-unused `"t"`/`"w"` variable blocks. | REQ-002, REQ-003 | done | Elasticity stays preprocessing (§12.1); `evaluate_demand_cap` itself is not modified. Also added `TIER_SEPARATOR`/`tier_scope_id`/`route_tier_scope_id` here as the one shared composite-key encoding, reused by T-003/T-004/T-006. |
| T-003 | Add `components/constraints/fee_tiers.py::FeeTierConstraint` (rows `tier_select`, `tier_capacity`, `tier_split`, plus the reserved-separator validation), and add the tiered-group skip to `components/constraints/demand.py`. | REQ-004, REQ-008, REQ-010 | done | The `demand_cap` skip is the one baseline-component change; it is guarded and inert without tiers. |
| T-004 | Add `components/objective_terms/tier_pricing.py::TierPricingTerm` contributing `P*tau*s_j*(f_gk - f_j^ref)` per `w_jk`, with `attribute()` recomputing the same and reporting a zero baseline. | REQ-005 | done | Delta construction leaves `fee_revenue` untouched; implemented as `fee_revenue_coefficient(route_at_tier) - fee_revenue_coefficient(route)` via `route.model_copy(update={"fee_rate": ...})`, so the variable-cost cancellation is guaranteed by reuse rather than re-derived. |
| T-005 | Extend `formulation/compiler_support.py` (`needs_mip`, `mip_required_issues`) and `formulation/mip.py`'s component tuples. | REQ-006 | done | One clause each; `compile_lp`'s rejection and the facade's dispatch then work with no further edits. `mip.py` also gained the `"t"` block's integrality marking (binary), alongside `z`/`n`. |
| T-006 | Add `domain/results.py::PricingSelection` and the defaulted `OptimizationResult.pricing` section; populate it in `reporting/result_builder.py`. | REQ-007 | done | Additive and defaulted, so existing results/tests are unaffected. `reference_fee_rate` mirrors `_compute_demand_caps`'s own incumbent-fee fallback (group's shared route fee, else the forecast's own reference). |
| T-007 | Add a `slow`-marked scale test sizing the `J*K` variable growth. | REQ-003 | todo | RISK-001; follows `specs/0005-test-hardening/`'s benchmark precedent. |
| T-008 | Tests: `tests/golden/test_fee_tier_pricing.py`, `tests/unit/test_fee_tier_compiler.py`, and `tests/unit/test_domain_contracts.py` additions. Confirm all pre-existing tests still pass (AC-009). | REQ-001 through REQ-010, NFR-001 through NFR-004 | todo | See Test Coverage Map, and `plan.md`'s worked fixture table — note the supply-sufficiency trap on the AC-002 fixture. **Resume here** — this is the next task. |
| T-009 | Update `specs/spec002/TRACEABILITY.md`: `LP-004` gains discrete-pricing evidence; `LP-009` gains the §12.4 / §14.1-seventh-trigger portion, with continuous nonlinear pricing and PWL interpolation explicitly still `SPECIFIED`. | REQ-001 through REQ-010 | todo | Mirrors the partial-status honesty already used for `LP-008`/`PLT-002`/`VER-005`. Do this only after T-008's tests actually pass — evidence pointers must cite real, passing tests. |
| T-010 | Update `docs/handoff.md` and `specs/README.md`: record this spec, note that Phase 3's deferred rate-ladder item and §14.1's seventh MIP trigger are closed by it, and restate what Phase 5 still leaves open (continuous NLP, multi-period). | REQ-001 through REQ-010 | todo | Phase 5 is *not* complete when this ships — only its item 1, in discrete form. Last task; do after T-007/T-008/T-009. |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | `test_fee_tier_pricing.py::test_reprices_up_when_demand_is_inelastic` | todo |
| AC-002 | `test_fee_tier_pricing.py::test_reprices_down_for_volume_when_elastic` | todo |
| AC-003 | `test_fee_tier_pricing.py::test_incumbent_tier_wins_when_supply_is_scarce` | todo |
| AC-004 | `test_fee_tier_compiler.py::test_compile_lp_rejects_tiered_request` | todo |
| AC-005 | `test_fee_tier_pricing.py::test_result_reports_menu_and_selection` | todo |
| AC-006 | `test_fee_tier_pricing.py::test_attribution_reconciles_and_matches_hand_delta` | todo |
| AC-007 | `test_domain_contracts.py::test_candidate_fee_rates_must_be_positive_increasing_unique` | todo |
| AC-008 | `test_fee_tier_compiler.py::test_reserved_separator_in_id_is_rejected` | todo |
| AC-009 | `test_fee_tier_compiler.py::test_untiered_request_index_is_unchanged`; existing suite (193) still passing | todo |
| AC-010 | `test_fee_tier_pricing.py::test_route_revenue_shares_honored_at_selected_tier` | todo |

## Follow-ups

Tracked work intentionally deferred (no silent "temporary" shortcuts — P8).

- **Phase 5 item 1's continuous form** — a true `NonlinearSolverBackend` (or sequential convex
  approximation) for continuous fee optimization, with §14.4's required convergence criteria,
  initialization policy, iteration cap, feasible fallback, and local-vs-global status. This spec
  deliberately builds §12.5's sanctioned discrete alternative instead; nothing here forecloses it.
- **Phase 5 item 2** — multi-period settlement and scenario-tree extensions, entirely untouched.
- **A distance-to-continuous-optimum error bound** for the candidate menu (`spec.md` Non-Goals) —
  only meaningful once a continuous solver exists to compare against.
- **True piecewise-linear interpolation** (§14.3's SOS2/segment machinery) for other curves such as
  tiered operating costs or recall-cost curves — a different mechanism from this spec's exact
  candidate evaluation, and still unbuilt.
- **A `REPRICED_TO_TIER` reason code** in `ReasonCode`, if a desk wants the selection narrated
  rather than reported structurally (`spec.md` Open Questions).
- **Migrating tiers to a versioned, approval-bearing pricing schedule** once the schedule subsystem
  (T29) exists — additive when it happens, and the natural home given §9.6's envelope.
