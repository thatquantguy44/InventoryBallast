# Plan: Test hardening against Section 24's Testing Strategy

- **Spec:** 0005-test-hardening (`spec.md`)
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code, implemented as described below)
- **Last updated:** 2026-09-05

> HOW. This plan requires an approved `spec.md`. Every requirement in the spec
> must appear in the traceability matrix below.

## Approach

Four additions, no changes to any already-passing test or to any production module except two
`TRACEABILITY.md` rows (REQ-014):

1. **`tests/property/test_lp_properties.py`** (new directory) — every `hypothesis`-based property
   (REQ-001 through REQ-005, REQ-007, REQ-008), each scoped to a narrow, hand-designed strategy
   layered on top of `tests/conftest.py`'s existing factories rather than a fully-generic "any
   valid request" generator (RISK-001).
2. **`tests/unit/test_lp_compiler.py`** gains two functions (REQ-009/010), matching its existing
   per-component style exactly (see the six tests already there).
3. **`tests/unit/test_scenarios_apply.py`** gains one function (REQ-006, empty-scenario-equals-
   baseline — deterministic, no `hypothesis` needed).
4. **`tests/golden/test_existing_loan_churn.py`** and **`tests/golden/
   test_utilization_floor_exceeds_cap.py`** (REQ-011/012) and **`tests/benchmark/
   test_core_desk_scale.py`** (REQ-013, marked `slow`).

`pyproject.toml` gains a `[tool.pytest.ini_options]` `markers` entry for `slow` (so
`pytest -m "not slow"` is a real, warning-free selector) and, if not already present, confirms
`hypothesis` stays a `dev` extra only (it already is).

## Property test designs (REQ-001 through REQ-005, REQ-007, REQ-008)

Each strategy is built with `st.composite`, generating a **single inventory record** with 1-3
routes (unless noted), varying only the few numeric fields each property actually needs and
holding everything else at safe, generous defaults (large `maximum_quantity_shares`, zero
`reserved_shares`/`committed_out_shares`, `elasticity=0.0` demand with `reference_quantity_shares`
larger than supply) so the *only* binding constraint is the inventory-balance row itself — this is
what keeps each property unconditionally true rather than "true unless some other cap binds"
(NFR-002).

```python
@st.composite
def _single_inventory_requests(draw, *, min_routes=1, max_routes=3):
    total_lendable = draw(st.floats(min_value=10.0, max_value=1000.0))
    n = draw(st.integers(min_value=min_routes, max_value=max_routes))
    fee_rates = draw(
        st.lists(st.floats(min_value=0.001, max_value=0.10), min_size=n, max_size=n, unique=True)
    )
    # Each route's own maximum is generous enough that inventory, not the route bound, binds.
    routes = tuple(
        route_factory(f"RT-{i}", f"DG-{i}", fee_rate=fee_rates[i], maximum_quantity_shares=total_lendable)
        for i in range(n)
    )
    demand = tuple(
        demand_factory(f"DG-{i}", f"BORROWER-{i}", fee_rate=fee_rates[i], reference_quantity_shares=total_lendable)
        for i in range(n)
    )
    inventory = inventory_factory(total_lendable_shares=total_lendable, available_to_lend_shares=total_lendable)
    return _build_request(inventory=(inventory,), routes=routes, demand=demand)
```

(`route_factory`/`demand_factory`/`inventory_factory` are the same fixtures `tests/conftest.py`
already exposes; the property module imports the underlying `make_*` helpers directly rather than
requesting fixtures inside a `@given`-decorated function, since `hypothesis` and pytest fixture
injection don't compose cleanly for the value the fixture *returns* — only for the factory
callables themselves, which are ordinary functions.)

- **REQ-001 (conservation) + REQ-008 (non-negativity), combined into one test function** to avoid
  solving twice for two properties that read the same generated example: solve the generated
  request, assert `verify_solution(...).passed` and `max_row_violation <= DEFAULT_TOLERANCE`
  (conservation), and assert every `AllocationRecord`/`BalanceRecord` numeric field is
  `>= -DEFAULT_TOLERANCE` (non-negativity). `max_examples=25` keeps this well under a second even
  with a real HiGHS solve per example.
- **REQ-002 (supply monotonicity)**: `min_routes=max_routes=1`. Draw `total_lendable` and a
  positive `delta`; solve at `total_lendable` and again at `total_lendable + delta` (same route/fee
  otherwise); assert the second allocation `>=` the first `- DEFAULT_TOLERANCE`.
- **REQ-003 (fee monotonicity)**: `min_routes=max_routes=2`, but overriding `_single_inventory_
  requests` to draw two fee rates with `assume(abs(fee_a - fee_b) >= 0.005)` (a fixed margin,
  ruling out near-tie degeneracy — RISK-001) and each route's `maximum_quantity_shares ==
  total_lendable` (so the higher-fee route can alone absorb all supply, making "higher fee wins"
  unconditional, not just usual). Assert the higher-fee route's allocation `>=` the lower-fee
  route's. A second sub-case re-solves with route A's fee raised further (`fee_a + bump`, guarding
  `assume` against landing exactly on `fee_b`) and asserts route A's own allocation doesn't
  decrease.
- **REQ-004 (elasticity monotonicity)**: no LP at all — calls `ConstantElasticityCurve.raw_demand`
  and `SemiLogElasticityCurve.raw_demand` directly. `elasticity` drawn from `[1e-6, 5.0]`,
  `reference_fee` from `[1e-4, 1.0]`, `fee_bump` from `[1e-4, 1.0]` (so `evaluated_fee =
  reference_fee + fee_bump` is strictly greater, never touching the `fee_floor`). Asserts both
  curves' `raw_demand(...)` return strictly less than `reference_quantity`.
- **REQ-005 (permutation invariance)**: `min_routes=2, max_routes=4`. Draw a `st.permutations`
  index order over `range(n)`; build the request twice — original order and permuted order for the
  `routes`/`demand` tuples (inventory is single-record here, so nothing to permute there); compile,
  solve, and compare `{route_id: post_quantity_shares for ...}` dicts (keyed by ID, so list order
  cannot matter) rather than raw list equality.
- **REQ-007 (scenario repeatability)**: draws a small `Scenario` (one `SELL` with a `quantity_shares`
  safely below `total_lendable`, or one `RateShock`) against a `_single_inventory_requests()`
  baseline; calls `run_scenario` twice; compares the two `ScenarioComparison.model_dump(mode="json")`
  outputs with `run_id`/`created_at` stripped from the nested result-shaped fields... in practice
  `ScenarioComparison` itself carries no `run_id`/`created_at` fields directly (only
  `baseline_run_id`/`scenario_run_id`, which *do* vary run to run) — those two plus nothing else
  need stripping, since `ScenarioComparison` does not embed `solver.runtime_seconds` anywhere (that
  lives on the two `OptimizationResult`s, which `ScenarioComparison` does not carry by reference).

## Dedicated constraint unit tests (REQ-009/010)

Mirror `test_lp_compiler.py`'s existing style exactly:

```python
def test_inventory_balance_row_matches_hand_formula(...) -> None:
    inventory = inventory_factory(
        total_lendable_shares=100.0, reserved_shares=10.0, committed_out_shares=5.0,
        on_loan_shares=15.0, available_to_lend_shares=70.0,
    )
    route = route_factory("RT-A", "DG-A", fee_rate=0.02, current_quantity_shares=15.0, ...)
    ...
    problem = compile_lp(request, default_config)
    row = problem.row_index.position(RowKey("inventory_balance", "INV-1"))
    assert problem.row_lower[row] == problem.row_upper[row] == pytest.approx(85.0)  # 100-10-5
    q_col = problem.variable_index.position(VariableKey("q", "RT-A"))
    a_col = problem.variable_index.position(VariableKey("a", "INV-1"))
    assert problem.constraint_matrix[row, q_col] == pytest.approx(1.0)
    assert problem.constraint_matrix[row, a_col] == pytest.approx(1.0)

def test_transition_identity_row_matches_hand_formula(...) -> None:
    route = route_factory("RT-A", "DG-A", fee_rate=0.02, current_quantity_shares=15.0, maximum_quantity_shares=80.0)
    ...
    problem = compile_lp(request, default_config)
    row = problem.row_index.position(RowKey("transition_identity", "RT-A"))
    assert problem.row_lower[row] == problem.row_upper[row] == pytest.approx(15.0)
    q_col, inc_col, dec_col = (problem.variable_index.position(VariableKey(k, "RT-A")) for k in ("q", "inc", "dec"))
    assert problem.constraint_matrix[row, q_col] == pytest.approx(1.0)
    assert problem.constraint_matrix[row, inc_col] == pytest.approx(-1.0)
    assert problem.constraint_matrix[row, dec_col] == pytest.approx(1.0)
```

## Golden fixture designs (REQ-011/012)

**Existing-loan churn (§24.5, REQ-011):** one inventory (100 shares, fully on loan), one existing
route (`RT-CURRENT`, fee 1.00%, `current_quantity_shares` == full supply, `maximum_quantity_shares`
== full supply), one candidate route (`RT-CANDIDATE`, fee 1.10%, `current_quantity_shares=0`,
`maximum_quantity_shares` == full supply). Each route keeps its own demand group with a generous
cap (100 shares, `elasticity=0`) — the competition that actually drives the churn decision is the
**shared inventory-balance row** (both routes draw on the same inventory record), matching E1's own
established two-route pattern; a shared demand group isn't needed for this property. Variant A:
`increase_cost_usd_per_share`/`decrease_cost_usd_per_share` on both routes set above the horizon
fee uplift (`price * tau * 0.001` for a 0.10% fee delta) — solved result: `RT-CURRENT`
unchanged, `RT-CANDIDATE` at 0. Variant B: both transition costs zero — solved result: inventory
moves to `RT-CANDIDATE` up to its demand maximum, `RT-CURRENT` drops correspondingly. §18.2's
attribution (already implemented, T11) must reconstruct both outcomes' objective exactly — the
test asserts `verification.passed` in both variants as the "objective attribution explains both
outcomes" check (§24.5's own wording), not a new assertion mechanism.

**Utilization floor exceeds cap (§24.6, REQ-012):** one inventory, one route with ample capacity
and demand. Two `UtilizationPolicy` records on the same `inventory_pool_id`: policy A sets
`maximum_utilization=0.30` alone (independently valid — no `minimum_utilization` on the same
record, so `UtilizationPolicy`'s own single-record ordering check never fires); policy B sets
`minimum_utilization=0.90` alone (equally independently valid). `UtilizationCapConstraint.
contribute()` (already implemented, T08) adds one row per policy per applicable inventory
record — so this produces two rows, `utilization_max <= 0.30*L` and `utilization_min >= 0.90*L`,
mutually exclusive for any positive `L`. Solved result: `INFEASIBLE`. This is the one §24.6 case
that's representable today without a domain-model change (see spec.md's Non-Goals for the
`CounterpartyLimit`-minimum case, which is not).

## Benchmark smoke test (REQ-013)

`tests/benchmark/test_core_desk_scale.py`, marked `@pytest.mark.slow`. Builds the Core desk shape
from `01_SPEC.md` §20.2 (5,000 inventory records, 50,000 routes, 20,000 demand groups) using
vectorized construction (list comprehensions over a fixed template, not per-row hand-authored
fixtures — Section 20.1's own vectorization principle applies to test fixtures too, or building
the fixture itself becomes the bottleneck rather than the solve). One inventory record and a
handful of routes/one demand group per "unit," repeated 5,000/10/20,000-ish times to hit the target
row counts approximately (exact ratios are illustrative, not a contract). Runs `compile_lp` +
`HighsBackend().solve(...)` + `verify_solution(...)` once, asserts `status is OPTIMAL` and
`verification.passed`, and asserts the combined wall-clock time (measured with
`time.perf_counter()`, not a `pytest-benchmark` plugin — no new dependency for one smoke test) is
under a **generous** ceiling (120 seconds) chosen to catch a catastrophic regression (e.g.
accidental O(n^2) construction) without being sensitive to normal machine-to-machine variance
(RISK-002). Excluded from the default `pytest tests/ -q` run via the `slow` marker;
`docs/handoff.md`'s Environment section gains the explicit opt-in invocation.

## Constitution Check

| Principle | Upheld? | Notes |
| --- | --- | --- |
| P4 Correct by construction | yes | Every property's scope is stated explicitly (narrow strategies, not "usually true"); the two golden fixtures cite exactly which spec sentence each numeric choice satisfies. |
| P5 Reversibility | yes | Purely additive test files; no production code changes except two `TRACEABILITY.md` row edits (prose only). |
| P6 Observability | yes | This whole spec exists to close an observability gap in the test suite itself — §24's own methodology wasn't being checked against reality until this audit. |
| P9 Security & data | yes | No secrets; the benchmark fixture is synthetic, generated in-process, never written to a committed file. |

## Traceability Matrix

| Requirement | Design element | Tasks |
| --- | --- | --- |
| REQ-001 | `tests/property/test_lp_properties.py::test_conservation_and_non_negativity` | T-001 |
| REQ-002 | `tests/property/test_lp_properties.py::test_supply_monotonicity` | T-001 |
| REQ-003 | `tests/property/test_lp_properties.py::test_fee_monotonicity` | T-001 |
| REQ-004 | `tests/property/test_lp_properties.py::test_elasticity_monotonicity` | T-001 |
| REQ-005 | `tests/property/test_lp_properties.py::test_permutation_invariance` | T-001 |
| REQ-006 | `tests/unit/test_scenarios_apply.py::test_empty_scenario_equals_baseline` | T-002 |
| REQ-007 | `tests/property/test_lp_properties.py::test_scenario_repeatability` | T-001 |
| REQ-008 | (same test as REQ-001) | T-001 |
| REQ-009 | `tests/unit/test_lp_compiler.py::test_inventory_balance_row_matches_hand_formula` | T-003 |
| REQ-010 | `tests/unit/test_lp_compiler.py::test_transition_identity_row_matches_hand_formula` | T-003 |
| REQ-011 | `tests/golden/test_existing_loan_churn.py` | T-004 |
| REQ-012 | `tests/golden/test_utilization_floor_exceeds_cap.py` | T-005 |
| REQ-013 | `tests/benchmark/test_core_desk_scale.py` | T-006 |
| REQ-014 | `specs/engine_spec/TRACEABILITY.md`'s `DOM-002`/`LP-002` rows | T-007 |
| NFR-001 | `max_examples` bounded per test (20-25) | T-001 |
| NFR-002 | Explicit `assume()`/margin guards documented above per property | T-001 |
| NFR-003 | `slow` pytest marker on the benchmark test | T-006 |

## Trade-offs & Alternatives

| Decision | Chosen | Rejected alternative | Why |
| --- | --- | --- | --- |
| Property strategies | Narrow, hand-scoped (single inventory, generous headroom) | A single generic "any valid `OptimizationRequest`" strategy | A fully generic strategy would need to encode every cross-record invariant (on-loan reconciliation, demand-group fee consistency, balance identity) inside the strategy itself to avoid constant `assume()`-driven rejection, which is a bigger, separate piece of infrastructure than eight targeted properties need. |
| Benchmark harness | A single smoke test with a generous wall-clock ceiling | A `pytest-benchmark`-based regression-tracking suite | Tracked-baseline regression detection is real, separate infrastructure (storage for historical runs, machine normalization) — out of scope for closing a "nothing exists" gap; `spec.md`'s Non-Goals says so explicitly. |
| Churn/utilization fixtures | Hand-constructed, cited against spec prose | Wait for an exact `EXAMPLES.md` numeric worked example | `EXAMPLES.md` doesn't have one for either case (confirmed by inspection); waiting indefinitely leaves the gap open. RISK-003 documents this trade explicitly rather than hiding it. |

## Validation Strategy

- `pytest tests/ -q` (the default, fast run) picks up every new test **except** the benchmark
  smoke test, via the `slow` marker.
- `pytest tests/ -m slow -q` runs the benchmark test on demand.
- `pytest tests/property/ -q -v` isolates the property module for focused runs while iterating.
- No leakage/backtest quant gates apply; `repro` (NFR-001) is the relevant one, checked by simply
  timing the property module's own run.

## Rollout, Observability & Rollback

Pure test additions; no production code changes beyond two `TRACEABILITY.md` prose edits.
Rollback is a plain revert of the new test files and those two edits. Observability is the tests
themselves; `docs/handoff.md` gains a one-line pointer to the `slow` marker's opt-in invocation.

## Open Questions

- Whether the benchmark test should eventually move into CI as an advisory (non-blocking) job once
  a remote exists — `spec.md`'s Open Questions defers this; not decided here.
