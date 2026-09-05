# Spec: Test hardening against Section 24's Testing Strategy

- **ID:** 0005-test-hardening
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted and implemented by Claude Code)
- **Approver:** Joshua Lutkemuller, CFA (chose "close the test gaps first" over proceeding straight to Phase 3)
- **Last updated:** 2026-09-05

> WHAT and WHY only. No implementation detail — that belongs in `plan.md`.

## Problem & Context

`specs/spec002/01_SPEC.md` §24 ("Testing Strategy") is a full normative section — not implied,
not optional. It lists eleven categories of tests every implementation is expected to carry:
unit (§24.1), property (§24.2), golden LP/elasticity/churn cases (§24.3-24.5), infeasibility
(§24.6), integration (§24.7), performance (§24.8), and — for subsystems not yet built —
Bloomberg-enrichment, eligibility/collateral/schedule, and agency/prime/platform tests
(§24.9-24.11). Unlike every other requirement in `01_SPEC.md`, §24 has **no dedicated
`specs/spec002/TRACEABILITY.md` rows of its own** (no `TST-*`/`QA-*` series) — it is a
cross-cutting methodology every other row's own "Evidence" column is expected to satisfy, not a
separately-tracked deliverable. That makes it easy for gaps to go unnoticed, which is exactly
what an audit against the actual test suite found (2026-09-05, 141 tests passing across T01-T14):

- **§24.2 property tests are not implemented at all.** `hypothesis` has been a pinned dev
  dependency (`pyproject.toml`) since T01, but is never imported anywhere in `tests/`. None of the
  eight listed properties (conservation, supply monotonicity, fee monotonicity, elasticity
  monotonicity, permutation invariance, empty-scenario-equals-baseline, scenario repeatability,
  non-negativity) has a property-based test.
- **`InventoryBalanceConstraint` and `TransitionIdentityConstraint` have no dedicated, isolated
  unit test.** Every other baseline component (`reserve_buffer`, `utilization_cap`,
  `counterparty_limit`, `demand_cap`, `fee_revenue`, `transition_cost`) has one in
  `tests/unit/test_lp_compiler.py`; these two only have *indirect* coverage (every golden test
  would fail if either broke, but nothing names them and pins their row/RHS formula the way the
  others are pinned).
- **§24.5's "existing-loan churn" case is not reproduced.** `transition_cost`'s mechanics are
  unit-tested generically (`test_transition_cost_coefficients_are_negative_on_inc_and_dec`), but
  the specific narrative — a 1.00% current route, a 1.10% candidate appears, high transition costs
  keep the book unchanged while zero transition costs let it churn — has no test of its own.
- **§24.6's infeasibility case list is only partially covered.** On-loan reconciliation (T04) and
  a hard-minimum-vs-reduced-supply conflict (E3, T13) both have tests. "Hard utilization floor
  exceeds cap" does not. "Counterparty minima conflict with hard counterparty maxima" **cannot be
  tested because it cannot happen**: `domain.policies.CounterpartyLimit` (T04, Phase 0A) only has
  `maximum_notional_usd`/`maximum_quantity_shares` fields — no minimum was ever added. This is a
  scope gap in the domain model, not a missing test, and this spec does not add one (see
  Non-Goals).
- **§24.8 performance/benchmark tests do not exist.** No test exercises any of the benchmark
  shapes `01_SPEC.md` §20.2 defines (Small/golden, Core desk, Agency desk, Stress).

This spec closes the gaps that are actually closeable today — property tests, the two missing
component unit tests, the churn golden case, the one representable infeasibility case, and a
smoke-scale benchmark harness — without inventing scope the domain model doesn't support yet.

## Goals

- A property-test module (`tests/property/test_lp_properties.py`), using `hypothesis` for real,
  covering conservation, supply monotonicity, single-route fee monotonicity, elasticity
  monotonicity, permutation invariance, empty-scenario-equals-baseline, scenario repeatability, and
  non-negativity — §24.2's full list, each scoped narrowly enough to stay true and non-flaky.
- Dedicated unit tests for `InventoryBalanceConstraint` and `TransitionIdentityConstraint` in
  `tests/unit/test_lp_compiler.py`, matching the existing per-component test style.
- A golden "existing-loan churn" test (§24.5) reproducing both the high-transition-cost
  (unchanged) and zero-transition-cost (churns) outcomes.
- A golden "hard utilization floor exceeds cap" infeasibility test (§24.6), constructed from two
  independently-valid `UtilizationPolicy` records whose *combination* (not either alone) conflicts.
- A basic benchmark smoke test (§24.8) at the "Core desk" shape from `01_SPEC.md` §20.2 (5,000
  inventory rows, 50,000 routes, 20,000 demand groups, 1,000 owners, 25 scenarios — the owner/
  scenario axes reduced to what this repo's baseline family actually uses), confirming compile +
  solve + verify completes and passes within a generous, non-flaky wall-clock ceiling.
- Close the stale `DOM-002` traceability note ("E3 scenario evidence pending T13") now that T13
  shipped, and strengthen `LP-002`'s evidence with the new dedicated constraint test.

## Non-Goals

- **A `CounterpartyLimit` minimum field** — §24.6's "counterparty minima conflict with hard
  counterparty maxima" case needs a domain-model addition this spec does not make. Adding a new
  field to an already-tested T04 contract, for one untested infeasibility case, is a bigger and
  separately-justified change; tracked as a follow-up only.
- **§24.9-24.11 (Bloomberg, eligibility/collateral/schedule, agency/prime/platform tests)** — the
  subsystems they test do not exist yet (T20-T24, T29-T32, T35-T40). Nothing to gap-check.
- **Strict, CI-enforced performance regression detection** — the benchmark test in this spec is a
  smoke test (does it complete, does it verify) with a generous ceiling, not a tight assertion on
  wall-clock time. Machine-dependent timing assertions belong in a dedicated benchmarking setup
  (e.g. a separate `pytest-benchmark` harness with tracked baselines), which is a larger, separate
  piece of infrastructure this spec does not build.
- **New TRACEABILITY.md row IDs for Section 24 itself** — `01_SPEC.md`'s own traceability scheme
  never assigned §24 a `TST-*`/`QA-*` series (it is cross-cutting methodology, not a row-tracked
  deliverable); this spec does not invent one. It strengthens or corrects existing rows (`DOM-002`,
  `LP-002`) instead.
- **Rewriting existing passing tests** — this spec only adds tests; it does not refactor
  `tests/unit/test_lp_compiler.py`'s existing per-component tests or any other already-passing
  test file.

## Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| REQ-001 | The system shall provide a `hypothesis`-based property test confirming inventory conservation: for randomly generated valid single/multi-route requests, the solved primal satisfies `sum(q_j) + a_i == total_lendable - reserved - committed` within `DEFAULT_TOLERANCE`. | must |
| REQ-002 | The system shall provide a property test confirming supply monotonicity: for a simple positive-economics single-route configuration, increasing `total_lendable_shares` never decreases that route's solved allocation. | must |
| REQ-003 | The system shall provide a property test confirming single-route fee monotonicity: for two routes sharing an inventory record with distinct, sufficiently-separated fee rates and ample capacity, the higher-fee route's allocation is never less than the lower-fee route's, and raising one route's fee (holding the other fixed) never decreases its own allocation. | must |
| REQ-004 | The system shall provide a property test confirming elasticity monotonicity: for `elasticity > 0` and `evaluated_fee > reference_fee`, `ConstantElasticityCurve.raw_demand` and `SemiLogElasticityCurve.raw_demand` both return a value strictly less than `reference_quantity`. | must |
| REQ-005 | The system shall provide a property test confirming permutation invariance: shuffling the order of a request's `inventory`/`routes`/`demand` tuples produces an identical solved result (allocations keyed by ID, not position). | must |
| REQ-006 | The system shall provide a test confirming that applying an empty `Scenario` (no trade events, no shocks) to a baseline produces a request equal to the baseline (aside from `request_id`'s scenario suffix) and a solved result identical to the baseline's, modulo `run_id`/`created_at`/`solver.runtime_seconds`. | must |
| REQ-007 | The system shall provide a property test confirming scenario repeatability: applying and solving the same non-trivial scenario twice produces identical `ScenarioComparison`s modulo the same three identity/wall-clock fields. | must |
| REQ-008 | The system shall provide a property test confirming non-negativity: for randomly generated valid requests, no solved allocation, balance, or availability quantity is negative beyond `DEFAULT_TOLERANCE`. | must |
| REQ-009 | The system shall provide a dedicated unit test for `InventoryBalanceConstraint` confirming its row's lower/upper bound equals `total_lendable_shares - reserved_shares - committed_out_shares` and its coefficients are exactly 1.0 on each participating route's `q` variable and the inventory's `a` variable. | must |
| REQ-010 | The system shall provide a dedicated unit test for `TransitionIdentityConstraint` confirming its row's bound equals `current_quantity_shares` and its coefficients are `+1` on `q`, `-1` on `inc`, `+1` on `dec`. | must |
| REQ-011 | The system shall provide a golden test reproducing §24.5's existing-loan churn case: a 1.00% current route fully allocated, a 1.10% candidate route, and both outcomes (unchanged when transition costs exceed the horizon fee uplift; churns to the higher-rate route when transition costs are zero). | must |
| REQ-012 | The system shall provide a golden test reproducing §24.6's "hard utilization floor exceeds cap" infeasibility case, built from two independently-valid `UtilizationPolicy` records whose combination (not either alone) is infeasible. | must |
| REQ-013 | The system shall provide a benchmark smoke test at the Core desk shape (§20.2) confirming `compile_lp` + `HighsBackend.solve` + `verify_solution` completes, returns `OPTIMAL`, and passes verification within a generous (non-flaky) wall-clock ceiling. | should |
| REQ-014 | The system shall correct `specs/spec002/TRACEABILITY.md`'s `DOM-002` row (remove the stale "E3 scenario evidence pending T13" note, now resolved) and strengthen `LP-002`'s evidence with the new `InventoryBalanceConstraint` unit test (REQ-009). | must |

## Non-Functional Requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | Test suite speed | The full property-test module completes in well under 30 seconds on a typical development machine (bounded `hypothesis` example counts per test — this repo's existing 141-test suite runs in under a second; property tests are the one place that changes, deliberately). |
| NFR-002 | No flaky properties | Every property test's generation strategy is scoped narrowly enough (via `assume()` or tight, hand-chosen bounds) that the property is unconditionally true within that scope — no "usually passes" tests. |
| NFR-003 | Benchmark test isolation | The Core desk benchmark test is marked so it can be skipped/deselected independently of the fast unit suite (e.g. a `pytest.mark.slow` marker), so `pytest tests/ -q`'s normal fast run is not made noticeably slower by it. |

## Acceptance Criteria

| ID | Given / When / Then | Covers |
| --- | --- | --- |
| AC-001 | Given `hypothesis`-generated valid requests (bounded route counts, positive fees, non-negative quantities), when each is solved, then every solution's inventory-balance residual is within `DEFAULT_TOLERANCE` of zero. | REQ-001 |
| AC-002 | Given a single-route config solved twice with `total_lendable_shares` increased the second time, when compared, then the second solve's route allocation is `>=` the first's. | REQ-002 |
| AC-003 | Given two routes on one inventory record with fee rates separated by at least a fixed margin and ample capacity/demand headroom, when solved, then the higher-fee route's allocation is `>=` the lower-fee route's. | REQ-003 |
| AC-004 | Given `elasticity > 0` and `evaluated_fee > reference_fee` (both `hypothesis`-generated within safe bounds), when `raw_demand` is called on both curve implementations, then both return strictly less than `reference_quantity`. | REQ-004 |
| AC-005 | Given a request and a randomly shuffled copy of the same request's `inventory`/`routes`/`demand` tuples, when both are compiled and solved, then the ID-keyed allocation/balance results are identical. | REQ-005 |
| AC-006 | Given a baseline solved once, when an empty `Scenario` is applied and solved, then the scenario request equals the baseline (aside from the ID suffix) and the scenario result matches the baseline result modulo `run_id`/`created_at`/`solver.runtime_seconds`. | REQ-006 |
| AC-007 | Given a `hypothesis`-generated non-trivial scenario (at least one trade event or shock) run twice via `run_scenario`, when the two `ScenarioComparison`s are compared (excluding the three identity/wall-clock fields), then they are identical. | REQ-007 |
| AC-008 | Given `hypothesis`-generated valid requests, when solved, then no `AllocationRecord`/`BalanceRecord` field representing a quantity is less than `-DEFAULT_TOLERANCE`. | REQ-008 |
| AC-009 | Given a request with reserved/committed shares set, when compiled, then `InventoryBalanceConstraint`'s row bound and coefficients match the hand-computed formula exactly. | REQ-009 |
| AC-010 | Given a route with a nonzero `current_quantity_shares`, when compiled, then `TransitionIdentityConstraint`'s row bound and coefficients match the hand-computed formula exactly. | REQ-010 |
| AC-011 | Given the churn fixture with transition costs exceeding the fee uplift, when solved, then the current route is unchanged; given zero transition costs, when solved, then inventory moves to the higher-rate route up to its demand maximum. | REQ-011 |
| AC-012 | Given two `UtilizationPolicy` records on the same inventory whose combined floor/cap conflict, when solved, then the result is `INFEASIBLE`. | REQ-012 |
| AC-013 | Given the Core desk benchmark fixture, when solved, then the result is `OPTIMAL`, verification passes, and wall-clock time is under the generous ceiling `plan.md` sets. | REQ-013 |
| AC-014 | Given `specs/spec002/TRACEABILITY.md` after this spec, when `DOM-002` and `LP-002` are inspected, then neither references a stale "pending T13" note and `LP-002`'s evidence names the new dedicated test. | REQ-014 |

## Data & Dependencies

- `hypothesis` (already a pinned dev dependency, `pyproject.toml`, never previously imported).
- `tests/conftest.py`'s existing factories (`inventory_factory`, `route_factory`, `demand_factory`)
  — reused as the base every property strategy varies a few parameters on top of, not replaced.
- `formulation.lp.compile_lp`, `solvers.highs.HighsBackend`, `validation.solution_verifier.
  verify_solution`, `facade.InventoryOptimizer`, `scenarios.apply.apply_scenario`,
  `scenarios.runner.run_scenario` — all already implemented; this spec only adds tests around them.
- `elasticity.constant.ConstantElasticityCurve`, `elasticity.semilog.SemiLogElasticityCurve` — read
  directly for REQ-004 (no LP solve needed for a pure curve-formula property).
- `01_SPEC.md` §20.2's benchmark shape table — the Core desk row, for REQ-013.

## Risks

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| RISK-001 | A property test's generation strategy is too broad and produces a false failure on a legitimate edge case (e.g. two routes tying exactly on fee), turning a correctness signal into noise. | Flaky tests get muted/ignored, silently losing the safety net they were meant to add. | NFR-002: every strategy is deliberately narrow (explicit margins between fee rates, `assume()` guards on demand/capacity headroom) rather than fully arbitrary; each property test documents exactly what scope it's true within. |
| RISK-002 | The Core desk benchmark test is slow enough to noticeably slow down every `pytest tests/ -q` run, encouraging people to stop running it. | The fast, sub-second test suite (a real, valued property of this repo today) degrades. | NFR-003: marked so it runs separately from the default fast suite; `plan.md`'s Validation Strategy states the exact invocation. |
| RISK-003 | The "existing-loan churn" and "utilization floor exceeds cap" golden fixtures are hand-constructed judgment calls (no exact numeric worked example is given in `EXAMPLES.md` for either) and could encode a wrong interpretation of §24.5/§24.6's prose. | A "golden" test that doesn't actually match the intended scenario gives false confidence. | Both fixtures' construction and expected outcome are stated explicitly in `plan.md`, citing exactly which spec sentence each numeric choice satisfies, so a reviewer can check the interpretation independently of trusting the test's own assertions. |

## Assumptions & Open Questions

- Assumption: "Core desk" benchmark shape (§20.2) uses the row's inventory/route/demand-group
  counts (5,000/50,000/20,000) but the owner (1,000) and scenario (25) axes don't apply to the
  baseline family's single-owner, single-solve shape today — the benchmark solves one large
  request once, not 25 scenario variants against 1,000 owners (that's the agency workstream,
  T35-T39, not yet built). Revisit the fixture's shape if/when agency lands.
- Open question: whether the benchmark test's wall-clock ceiling should be wired into CI at all
  (even loosely) or run only on demand. `plan.md` marks it `slow` and excludes it from the default
  `pytest tests/ -q` run; CI wiring is a separate follow-up.

## Exceptions

None recorded.
