# Tasks: Expected economics and entity-hierarchy realism (Realism release R1)

- **Spec:** 0012-expected-economics-realism (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-15

> Ordered, testable units of work. Every task cites the requirement(s) it advances and carries a
> Definition of Done. No task without a requirement.

**Status note:** `spec.md` is **Approved**. Owner decisions are resolved:
`expected_shadow` is the default, `expected_direct` is explicit opt-in, T24's PWL unwind cost is
deferred to a future spec, hard entity-scoped limits fail closed on unresolved/low-confidence/
conflicting mappings, and the R-numbering documentation correction is accepted. Slice A (T-001
through T-004) and the Slice B input/context work (T-005 through T-006) are implemented; remaining
Slice B/C work is todo.

Tasks are grouped by the three independent slices in `plan.md`. The slices share no code path, so
they can be implemented and reviewed in any order — or split across separate branches if the review
is easier that way.

## Definition of Done (applies to every task)

- Code matches `plan.md`; deviations noted there before merge, not silently.
- Tests exist and pass deterministically (`pytest tests/ -q`).
- Every existing test continues to pass unchanged (NFR-001) — run the full suite after every task.
- With nothing supplied and the default `expected_shadow` mode, the compiled problem is
  byte-identical to today: same variables, rows, bounds, and objective coefficients.
- The compiled problem remains an LP (NFR-005); `needs_mip`/`needs_qp` are untouched.
- No estimation, fitting, or training anywhere under `src/inventory_optimizer` (NFR-003).
- No secrets, credentials, or private data introduced; estimate fixtures carry obviously-fake model
versions.
- `specs/engine_spec/TRACEABILITY.md` and `docs/handoff.md` are updated alongside the change that
  closes them (T-012, T-013), only once real, passing tests exist to cite.

## Task List

### Slice A — entity hierarchy (T22)

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-001 | Add `EntityRelationship` to `domain/reference.py` and `enrichment/entity_hierarchy.py::resolve_hierarchy`, delegating candidate selection to `0011`'s unchanged `resolve_latest_known`. | REQ-001, REQ-002 | done | Do not write a second time-resolution implementation — the no-look-ahead guarantee (AC-003) must be inherited, not reimplemented. |
| T-002 | Add `ports/entity_data.py` and a synthetic `adapters/bloomberg/entities.py`, following `0011`'s port/synthetic-adapter pattern exactly. | REQ-001, REQ-002 | done | `0011` deliberately did not create these because nothing consumed them; this task is where they earn their place. |
| T-003 | Add optional `legal_entity_id`/`ultimate_parent_id` to `CounterpartyLimit`; compute `routes_by_entity`/`routes_by_ultimate_parent` in `formulation/context.py`; widen `counterparty.py`'s route-set lookup. | REQ-003 | done | The rows themselves are unchanged — only membership widens. A limit with neither field set must take exactly today's code path. |
| T-004 | Implement §22.9's fail-closed rule for hard entity-scoped limits (unresolved / low-confidence / conflicting), with a configurable `minimum_entity_confidence`; warn instead for non-hard limits. | REQ-004 | done | Owner decision confirmed: credit limits are controls, so hard aggregation fails closed. |

### Slice B — expected economics (T23)

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-005 | Add `domain/economics.py::ExpectedEconomics` with §22.5's coefficients plus the required `model_version`/`calibration_date`/`uncertainty` on every record. | REQ-005 | done | Estimates are inputs; nothing in this repo produces them (NFR-003). |
| T-006 | Precompute `expected_active_fraction` (clamped to `[0, 1]`) and the additive expected costs in `formulation/context.py`; expose both on `BuildContext`. | REQ-006 | done | Same slot and same discipline as `demand_caps`/`tier_caps`: computed once, before model construction. |
| T-007 | Extend `fee_revenue_coefficient` with the optional `expected_active_fraction` parameter; add `objective_terms/expected_costs.py` for the additive per-route costs. | REQ-007 | todo | `None` at every existing call site is what makes NFR-001 structural. Do not scale `transition_cost` (RISK-004 — `plan.md` pins why). |
| T-008 | Add `ObjectiveConfig.economics_mode` (default `expected_shadow`) with explicit `expected_shadow`, `expected_direct`, and `contractual` values; wire `expected_direct` mode through the compilers; fail closed when a route lacks an estimate in `expected_direct` mode. | REQ-008, REQ-010, NFR-004 | todo | A config predating this field must remain valid and mean `expected_shadow`, which remains byte-identical to today's solve when no estimates are supplied. |
| T-009 | Implement default shadow mode: in `expected_shadow` mode with estimates supplied, compute expected economics post-solve against the already-solved quantities and attach the comparison — changing no coefficient, bound, or allocation. | REQ-009 | todo | Same shape as `0010`'s projection: report against a solved result, never re-optimize. AC-006 pins the byte-identical requirement. |
| T-010 | Add the additive, defaulted `OptimizationResult.economics` disclosure section (mode, per-route model version/calibration date/uncertainty, shadow comparison). | REQ-011 | todo | Additive and defaulted, so no existing result or test changes — `0009`'s `pricing` section is the precedent. |

### Slice C — dynamic buffer (T24, buffer half only)

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-011 | Add `DynamicBuffer` with §22.7's five named components; fold them into `ReserveBufferConstraint`'s existing `max(...)` tracking which candidate bound; report the binding component. | REQ-012, REQ-013, REQ-014 | todo | Precomputed, so the default stays an LP (§22.7, verbatim). Absent a `DynamicBuffer`, the bound must be byte-identical to today's. |

### Cross-cutting

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-012 | Tests: `test_domain_entity.py`, `test_entity_hierarchy.py`, `test_entity_limits.py`, `test_domain_economics.py`, `test_expected_economics_context.py`, `test_expected_economics.py`, `test_dynamic_buffer.py`, `tests/golden/test_expected_economics.py`, a `hypothesis` clamp property test, and an architecture-boundary addition for NFR-003. Confirm the full pre-existing suite (326 passed) still passes unchanged. | REQ-001 through REQ-015, NFR-001 through NFR-005 | todo | See Test Coverage Map below. Write each slice's byte-identical regression check *before* its behavior tests. |
| T-013 | Update `specs/engine_spec/TRACEABILITY.md`: add `DAT-005` evidence and the §22.9 entity rows; **restore the `DAT-001`-`DAT-004`/`DAT-006` release tags `0011` incorrectly changed from `R3` to `R0`**, and add a one-line note naming which R-numbering the release column uses. | REQ-001 through REQ-015 | todo | Owner decision accepted. This corrects a real error introduced by `0011`, so it lands whether or not the rest of this spec proceeds. |
| T-014 | Update `docs/handoff.md` and `specs/README.md`: record this spec as Implemented, state plainly that G3 remains un-granted, `expected_direct` ships off by default, `expected_shadow` is the default, and restate what R1 still leaves open (PWL unwind cost, T25-T28). | REQ-001 through REQ-015 | todo | Last task. The handoff/README now record this spec as Approved; this upgrades those entries to Implemented after code and tests land. |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | `test_entity_limits.py::test_parent_scoped_limit_aggregates_across_borrowers` | todo |
| AC-002 | `test_entity_limits.py::test_low_confidence_mapping_fails_closed_for_hard_limit` | todo |
| AC-003 | `test_entity_hierarchy.py::test_relationship_observed_later_is_invisible` | todo |
| AC-004 | `test_expected_economics_context.py::test_expected_active_fraction_formula_and_clamp` | done |
| AC-005 | `tests/golden/test_expected_economics.py::test_expected_direct_shifts_allocation_to_higher_take_up` | todo |
| AC-006 | `test_expected_economics.py::test_expected_shadow_with_estimates_is_byte_identical` | todo |
| AC-007 | `test_expected_economics.py::test_expected_direct_fails_closed_on_missing_estimate` | todo |
| AC-008 | `test_expected_economics.py::test_expected_direct_attribution_reconciles_and_matches_hand_computed_expected_revenue` | todo |
| AC-009 | `test_expected_economics.py::test_result_discloses_mode_and_estimate_lineage` | todo |
| AC-010 | `test_dynamic_buffer.py::test_liquidity_component_binds_and_is_reported`, `::test_no_dynamic_buffer_is_byte_identical` | todo |
| AC-011 | `test_expected_economics.py::test_all_three_slices_together_stay_lp` | todo |
| AC-012 | full suite (`pytest tests/ -q`, 326-passed baseline preserved) | todo |

## Follow-ups

Tracked work intentionally deferred (no silent "temporary" shortcuts — P8).

- **T24's piecewise-linear liquidity/unwind cost** (§22.7's `PWL_i(v_i; knots)`) — deferred to its
  own future spec by owner decision. Needs segment variables, a convexity argument (a convex
  cost under a maximizing objective is self-selecting without binaries, which would keep it LP —
  but that must be proved, not assumed), §14.3's breakpoint disclosure, and its own benchmark.
- **Granting G3** — "Expected-economics model promotion" (`ROADMAPS.md` §7), owned by quant
  research + model risk + business. Nothing in this repo grants it; `expected_direct` stays off by
  default until it is.
- **An upstream estimator** for take-up/survival/repricing/liquidity. Out of scope by §22.13; this
  spec defines the contract it must satisfy.
- **Reinvestment income (`r_j * h_j`)** — §22.5's formula includes it; `objective_terms/
  reinvestment.py` has never been built (§28 defers it).
- **A first-class borrower netting-set contract** (§22.9's own wording), if agency/prime work
  (T36-T39) needs more than `CounterpartyLimit`'s two optional entity fields.
- **R2 (T25-T27):** censoring-aware hierarchical elasticity, robust/CVaR scenarios, and
  multi-period balances beyond `0010`. Each needs separate model-risk approval (`G5`/`G6`).
