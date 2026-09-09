# Tasks: Test hardening against Section 24's Testing Strategy

- **Spec:** 0005-test-hardening (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-05

> Ordered, testable units of work. Every task cites the requirement(s) it advances
> and carries a Definition of Done. No task without a requirement.

**Status:** implemented (2026-09-05). All 14 ACs pass; 153 tests pass in the default `pytest
tests/ -q` run (the Core desk benchmark is `slow`-marked and runs separately via `pytest tests/ -m
slow -q`, completing in ~1.2s at 5,000 inventory / 50,000 route / 25,000 demand-group scale — well
under the 120s ceiling). Ruff clean.

## Definition of Done (applies to every task)

- Code matches `plan.md`; deviations noted there before merge, not silently.
- Tests exist and pass deterministically (`pytest tests/ -q` for fast tests; `pytest tests/ -m slow
  -q` for the benchmark test).
- No secrets, credentials, or private data introduced.
- No already-passing test is modified or weakened.
- `specs/engine_spec/TRACEABILITY.md`'s `DOM-002`/`LP-002` rows are updated alongside T-007, not
  deferred to a later commit.

## Task List

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-001 | Add `tests/property/test_lp_properties.py`: conservation+non-negativity, supply monotonicity, fee monotonicity, elasticity monotonicity, permutation invariance, scenario repeatability — six `hypothesis`-based test functions per `plan.md`'s designs. | REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-007, REQ-008, NFR-001, NFR-002 | done | Bound `max_examples` per test (20-25); every strategy documented with the scope it's true within. |
| T-002 | Add `tests/unit/test_scenarios_apply.py::test_empty_scenario_equals_baseline`. | REQ-006 | done | Deterministic, no `hypothesis`. |
| T-003 | Add `tests/unit/test_lp_compiler.py::test_inventory_balance_row_matches_hand_formula` and `test_transition_identity_row_matches_hand_formula`. | REQ-009, REQ-010 | done | Matches the file's existing per-component test style exactly. |
| T-004 | Add `tests/golden/test_existing_loan_churn.py` (§24.5, both variants). | REQ-011 | done | Fixture cites the exact spec sentence each numeric choice satisfies (RISK-003). |
| T-005 | Add `tests/golden/test_utilization_floor_exceeds_cap.py` (§24.6). | REQ-012 | done | Two independently-valid `UtilizationPolicy` records; the conflict only exists in combination. |
| T-006 | Add `tests/benchmark/test_core_desk_scale.py`, marked `@pytest.mark.slow`; register the `slow` marker in `pyproject.toml`. | REQ-013, NFR-003 | done | Vectorized fixture construction; generous (120s) wall-clock ceiling, not a tight regression assertion. |
| T-007 | Update `specs/engine_spec/TRACEABILITY.md`: remove `DOM-002`'s stale "E3 scenario evidence pending T13" note (now resolved by `specs/0004-scenario-engine/`); add the new `InventoryBalanceConstraint` test to `LP-002`'s evidence. | REQ-014 | done | Prose-only change; neither row's `IMPLEMENTED` status changes. |
| T-008 | Update `docs/handoff.md`: note the closed test-coverage gaps and the `slow`-marker opt-in invocation; mark this spec done. | REQ-001 through REQ-014 | done | |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | `test_lp_properties.py::test_conservation_and_non_negativity` | done |
| AC-002 | `test_lp_properties.py::test_supply_monotonicity` | done |
| AC-003 | `test_lp_properties.py::test_fee_monotonicity` | done |
| AC-004 | `test_lp_properties.py::test_elasticity_monotonicity` | done |
| AC-005 | `test_lp_properties.py::test_permutation_invariance` | done |
| AC-006 | `test_scenarios_apply.py::test_empty_scenario_equals_baseline` | done |
| AC-007 | `test_lp_properties.py::test_scenario_repeatability` | done |
| AC-008 | `test_lp_properties.py::test_conservation_and_non_negativity` (same test as AC-001) | done |
| AC-009 | `test_lp_compiler.py::test_inventory_balance_row_matches_hand_formula` | done |
| AC-010 | `test_lp_compiler.py::test_transition_identity_row_matches_hand_formula` | done |
| AC-011 | `test_existing_loan_churn.py` | done |
| AC-012 | `test_utilization_floor_exceeds_cap.py` | done |
| AC-013 | `test_core_desk_scale.py` | done |
| AC-014 | Manual: `specs/engine_spec/TRACEABILITY.md` diff reviewed against the traceability update above | done |

## Follow-ups

Tracked work intentionally deferred (no silent "temporary" shortcuts — P8).

- A `CounterpartyLimit` minimum field (needed for §24.6's "counterparty minima conflict with hard
  counterparty maxima" case) waits on a real need — see `spec.md` Non-Goals.
- §24.9-24.11 (Bloomberg, eligibility/collateral/schedule, agency/prime/platform tests) wait on
  their owning subsystems (T20-T24, T29-T32, T35-T40).
- Tracked-baseline performance-regression detection (vs. this spec's one-off smoke test) is
  untracked by any task yet.
- Wiring the `slow`-marked benchmark test into CI (advisory or blocking) waits on a GitHub remote
  existing and a decision on cadence.
