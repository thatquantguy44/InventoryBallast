# Handoff

The roadmap a new owner (human or agent) reads first. Keep this in sync: a new
`specs/NNNN-*` directory should land with an edit here (enforced by the
`handoff-sync` gate).

## What this repo is

InventoryBallast is a portable, solver-neutral securities-lending inventory
optimization engine. It was extracted (2026-09-04) from the `QR-Haven` monorepo's
`projects/inventory_optimizer/` into its own repository, preserving that
directory's original 6 commits via `git subtree split`. It started as a local-only
repo by the owner's choice at extraction time; a GitHub remote
(`thatquantguy44/InventoryBallast`) now exists (since ~2026-09-09) — see "Open
items" below for its current state and a real gap CI surfaced once it did.

It also adopts the [QuantSmith](https://github.com/joshualutkemuller/QuantSmith)
agentic scaffold (`instructions/`, `hooks/`, `agents/`, `prompts/`, `templates/`,
`CLAUDE.md`) and pins the `quantsmith` package as an optional dependency. See
`CLAUDE.md` for the operating model and `docs/adoption_guide.md`-equivalent
guidance lives in the QuantSmith repo itself (not copied here — see "Open items"
below).

## The actual spec: `specs/engine_spec/`

The engine's normative specification is [`specs/engine_spec/`](../specs/engine_spec/) —
copied over from `QR-Haven` in the same extraction (it was **not** carried by the
`git subtree split`, since it lived outside `projects/inventory_optimizer/` in the
monorepo; it was copied separately and is new, uncommitted-by-QuantSmith content
specific to this engine, not the QuantSmith reference spec). Read in this order,
per `specs/engine_spec/00_PLAN.md`'s own "Handoff Order":

1. `01_SPEC.md` §4 — boundaries and vocabulary
2. `01_SPEC.md` §7 — target project structure
3. `01_SPEC.md` §9 — data contracts and invariants
4. `01_SPEC.md` §11-12 — LP formulation and elasticity
5. `01_SPEC.md` §15-16 — component/solver interfaces
6. `01_SPEC.md` §13 — scenario semantics
7. `01_SPEC.md` §22 — Bloomberg-enriched realism, source-of-truth rules
8. `01_SPEC.md` §23 — platform integration, agency/prime desk models
9. `EXAMPLES.md` — worked examples and golden-update policy
10. `TRACEABILITY.md` — requirement-to-evidence mapping, phased definition of done

`specs/0001-daily-momentum-signal/` is unrelated — it's QuantSmith's own reference
spec, copied in as a worked example of the SDD chain, not part of InventoryBallast's
scope.

## Current state (verified 2026-09-07)

Per `specs/engine_spec/00_PLAN.md`'s status line and `TRACEABILITY.md`:

- **Implemented and tested:** T01-T18, T34, and the `securities_lending_inventory`
  baseline of T35 — package scaffold, domain contracts, config, elasticity
  (`elasticity/`), sparse LP formulation (`formulation/`), the baseline LP compiler
  (`formulation/lp.py::compile_lp`), the HiGHS backend (`solvers/highs.py`), the
  independent solution verifier (`validation/solution_verifier.py`), T11's
  result/attribution/explainability layer (`reporting/`;
  `specs/0002-result-attribution-explainability/`), T12's public API facade + CLI
  (`facade.py`, `services.py`, `cli.py`; `specs/0003-public-api-cli/`), T13-T14's
  scenario engine plus a basic stress-testing capability (`scenarios/`,
  `domain/scenarios.py`, `domain/scenario_results.py`;
  `specs/0004-scenario-engine/`), T15's Phase 3 MIP business rules
  (`formulation/mip.py::compile_mip`, `components/constraints/mip_rules.py`,
  `formulation/compiler_support.py`; `specs/0006-mip-business-rules/`), T18's
  Phase 4 QP allocation-stability penalty (`formulation/qp.py::compile_qp`,
  `components/objective_terms/allocation_stability.py`,
  `formulation/qp_support.py`; `specs/0007-qp-allocation-stability/`), and the
  tabular result output layer (`reporting/tables.py`, `adapters/`;
  `specs/0008-tabular-result-output/`), and Section 12.4's discrete fee-tier
  pricing MIP (`components/constraints/fee_tiers.py`,
  `components/objective_terms/tier_pricing.py`, `domain/results.py::
  PricingSelection`; `specs/0009-discrete-fee-tier-pricing/`). 239 tests pass
  (2 skipped for the absent `pandas` extra) in the default `pytest tests/ -q`
  run (with the `highs` extra installed), plus a real `pip install -e .`
  console script (`inventory-optimizer`, including working
  `scenarios`/`tables` subcommands) and three `slow`-marked benchmark smoke
  tests (Core-desk-scale LP from `specs/0005-test-hardening/`; moderate-scale
  QP from `specs/0007-qp-allocation-stability/`; moderate-scale fee-tier MIP
  from `specs/0009-discrete-fee-tier-pricing/`) run separately.
- **Test coverage hardened against `01_SPEC.md` §24 (2026-09-05):** an audit
  against the normative "Testing Strategy" section found `hypothesis` (a pinned
  dev dependency since T01) had never actually been used; `specs/0005-test-
  hardening/` closes that and four other real gaps — see its entry below.
- **Done (2026-09-09):** `specs/0010-multi-period-settlement/` (Phase 5 item 2; `01_SPEC.md` §22.11)
  — both the deterministic projection (Phase 1, `settlement/`) and the joint multi-period LP
  (Phase 2, `formulation/multi_period.py::solve_multi_period`), all fourteen tasks (`T-001`-`T-014`)
  done; see its own entry below. 275 tests pass (2 skipped for the absent `pandas` extra) in the
  default run, plus a separate `slow`-marked scale benchmark.

## Environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,highs,dataframe,agentic]"
.venv/bin/python -m pytest tests/ -q         # 275 passed, 2 skipped (pandas absent), as of this writing (fast; excludes `slow`)
.venv/bin/python -m pytest tests/ -m slow -q # 4 benchmark smoke tests (Core desk LP, QP, fee-tier, multi-period LP scale)
inventory-optimizer doctor                    # sanity-check the installed console script
```

See `README.md`'s "Development" section for the extras breakdown. `.venv/` is
gitignored — recreate it rather than expecting it to be there.

## Next priorities, in order

### T11 — Result, attribution, and explainability (`01_SPEC.md` §18) — done (2026-09-04)

`specs/0002-result-attribution-explainability/` (`spec.md`, `plan.md`,
`tasks.md`) — the first real `NNNN-slug` SDD spec in this repo, shaped with
`agents/optimization/problem_formulation/` and
`agents/optimization/solver_diagnostics_sensitivity/` per the routing table
below. All eleven tasks (`T-001`-`T-011`) are done: the `reporting/` package
(`types.py`, `attribution.py`, `explanations.py`, `shadow_prices.py`,
`result_builder.py`), the thirteen new `domain/results.py` section models, and
10 new tests under `tests/unit/reporting/` (107 total, all passing).

What shipped, per §18: a full `OptimizationResult` assembly
(`reporting.result_builder.build_optimization_result`) covering all fifteen
§18.1 sections (Schedules/Collateral/Sources are explicit `None` — no upstream
domain model exists yet for them); objective attribution
(`reporting.attribution.attribute_objective`) that independently recomputes
each component's unscaled USD value and hard-fails
(`AttributionMismatchError`) if the sum disagrees with the solver's own
claimed objective; decision explanations (`reporting.explanations.explain_routes`)
deriving 3 of the 24 `ReasonCode` values so far (`HIGHER_NET_FEE`,
`DEMAND_CAP_BINDING`, `ELASTICITY_REDUCED_DEMAND`; the remaining 21 wait on
their owning constraint components — see the spec's tasks.md Follow-ups); and
LP shadow prices (`reporting.shadow_prices.build_shadow_prices`), correctly
omitted whenever the backend reports no dual (MIP solves).

`specs/engine_spec/TRACEABILITY.md` rows `LP-007`, `VER-001`, `VER-002`,
`VER-005`, `VER-006` moved `SPECIFIED` → `IMPLEMENTED`. `LP-008` was
**not** closed — the original spec draft incorrectly listed it; it needs the
joint collateral mode (T32, not started), not just T11, and was corrected in
`spec.md`'s Goals section before merge.

### T12 — Public API and CLI (`01_SPEC.md` §17) — done (2026-09-05)

`specs/0003-public-api-cli/` (`spec.md`, `plan.md`, `tasks.md`) — drafted by a
background agent following T11's spec as its template, reviewed, and approved
(the draft's three flagged decisions — the `formulation/context.py::
build_context()` extraction, the CLI exit-code scheme, and `load_config`'s
reduced scope — were signed off before implementation). All fourteen tasks
(`T-001`-`T-014`) are done: `services.py` (`OptimizationService`,
`ExplanationService`, `ExplanationServiceImpl`), `facade.py`
(`InventoryOptimizer`, `load_config`), `cli.py` (`validate|optimize|scenarios|
components|doctor`), a new `formulation/context.py::build_context()` (a
same-behavior extraction `compile_lp` now calls internally), the
`inventory-optimizer` console script (`pyproject.toml`'s `[project.scripts]`),
and 18 new tests (`tests/unit/test_facade.py`, `test_services.py`, `test_cli.py`,
`tests/golden/test_e1_cli_end_to_end.py` — 125 total, all passing).

Two real bugs surfaced only by wiring the facade end to end and are fixed, not
worked around (see `specs/0003-public-api-cli/plan.md`'s "Deviations Discovered
During Implementation" for the full account): `OptimizationRequest`'s and T11's
`AllocationRecord`'s `MappingProxyType`-defaulted fields could not be
serialized at all (`domain/requests.py`, `domain/results.py` now carry a
`@field_serializer` each); and `SolverDiagnostics.runtime_seconds` is
genuinely non-deterministic run-to-run (wall-clock solve time), which
corrected `spec.md`'s determinism claims (`NFR-001`/`NFR-004`/`AC-002`/`AC-011`)
rather than the code.

`specs/engine_spec/TRACEABILITY.md`'s `PLT-002` row gained an evidence pointer to
`tests/golden/test_e1_cli_end_to_end.py` but stays `SPECIFIED` — its `G2C`
gate is a cross-cutting platform-ownership release approval shared with
`PLT-001`, `PLT-003`-`PLT-006` (all T17/T34-owned, none of which this repo
builds), not something T12 grants unilaterally.

### T13-T14 — Scenario engine and basic stress testing (`01_SPEC.md` §13; Phase 2) — done (2026-09-05)

`specs/0004-scenario-engine/` (`spec.md`, `plan.md`, `tasks.md`) — all ten
tasks (`T-001`-`T-010`) done: `domain/scenarios.py` (`TradeEvent` — all seven
§13.1 types — `RateShock`, `DemandShock`, `Scenario`), `domain/
scenario_results.py` (`ScenarioComparison`, `StressTestReport`), the
`scenarios/` package (`apply.py::apply_scenario`, `compare.py::
build_scenario_comparison`, `runner.py::run_scenario`/`run_scenarios`/
`run_stress_test`), `services.ScenarioService` (finally defined, unblocking
T12's own deferral), and a real `inventory-optimizer scenarios` CLI
subcommand (single scenario file or a batch array). 16 new tests (141 total,
all passing) — including `tests/golden/test_e2_rate_shock_scenario.py` and
`test_e3_sale_and_recall_scenario.py`, which reproduce `EXAMPLES.md`'s E2 and
E3 **exactly**, with zero changes to `reporting/`, `formulation/`, or
`validation/`.

**Basic stress testing** (added at the owner's request, beyond `01_SPEC.md`
§13's own text, so it carries no `specs/engine_spec/TRACEABILITY.md` row of its
own): `scenarios.runner.run_stress_test(baseline_request, baseline_result,
scenarios, optimizer) -> StressTestReport` runs a batch of (typically
adverse) scenarios and summarizes worst-case degradation in one report —
feasible/infeasible/verification-failed counts, and the single worst-case
scenario by objective delta among the feasible ones. Library function only
so far; no CLI subcommand yet (`specs/0004-scenario-engine/tasks.md`'s
Follow-ups) — a natural next increment once a real stress-testing workflow
exists.

Two design notes worth reading before extending this further (both in
`specs/0004-scenario-engine/plan.md`): (1) a scenario-modified request is
deliberately never round-tripped through `model_validate`/JSON reload before
solving — that's what lets a `SELL` legitimately represent an "oversold,
pending recall" book state (E3's own setup) without a `SecurityInventory`
domain-model change; `ScenarioComparison.warnings` surfaces that state
explicitly rather than hiding it. (2) `schedule_overlays`, `collateral_shocks`,
`desk_events`, `InventoryShock`, and `PolicyOverride` are all deliberately
**not** implemented — `specs/engine_spec/TRACEABILITY.md`'s `SCN-004` row stays
`SPECIFIED` (tagged `T40`); the rest wait on T29/T30-T32/T35-T39 or a real
worked example to pin their shape down.

### Test hardening against `01_SPEC.md` §24 — done (2026-09-05)

`specs/0005-test-hardening/` (`spec.md`, `plan.md`, `tasks.md`) — prompted by
a direct question ("is a robust validation/testing suite in the spec, along
with unit testing for each part of the model?"). §24 ("Testing Strategy") is
a full normative section; auditing the actual suite against its eleven
subsections found five real, closeable gaps, all now closed (all eight
`tasks.md` tasks done):

- **§24.2 property tests, not implemented at all** despite `hypothesis`
  being a pinned dev dependency since T01 — `tests/property/
  test_lp_properties.py` now covers all eight listed properties (conservation,
  supply/fee/elasticity monotonicity, permutation invariance, empty-scenario-
  equals-baseline, scenario repeatability, non-negativity), each scoped
  narrowly enough to stay unconditionally true (documented per-test, not
  "usually passes").
- **`InventoryBalanceConstraint`/`TransitionIdentityConstraint`** had no
  dedicated, isolated unit test (only indirect golden-solve coverage) —
  `tests/unit/test_lp_compiler.py` gained one each, strengthening
  `specs/engine_spec/TRACEABILITY.md`'s `LP-002` evidence.
- **§24.5's existing-loan-churn case** (1.00% current route vs. a 1.10%
  candidate, transition-cost-gated) reproduced in
  `tests/golden/test_existing_loan_churn.py`.
- **§24.6's "hard utilization floor exceeds cap" infeasibility case**
  reproduced in `tests/golden/test_utilization_floor_exceeds_cap.py` (two
  independently-valid `UtilizationPolicy` records whose *combination*
  conflicts). The other §24.6 case in that bullet — counterparty minima vs.
  maxima — genuinely cannot be tested: `CounterpartyLimit` has no minimum
  field. Tracked as a follow-up, not silently skipped.
- **§24.8 performance tests, none existed** — `tests/benchmark/
  test_core_desk_scale.py` (`@pytest.mark.slow`, excluded from the default
  run via `pyproject.toml`'s `addopts`) is a smoke test, not tracked-baseline
  regression detection: at the Core desk shape (~5,000 inventory / 50,000
  route / 25,000 demand-group records), compile+solve+verify completes in
  ~1.2s, well under the 120s ceiling chosen to catch a catastrophic
  regression without machine-variance flakiness.

§24.9-§24.11 (Bloomberg, eligibility/collateral/schedule, agency/prime/
platform tests) are correctly untested — those subsystems don't exist yet,
so there is nothing to gap-check; not a finding.

### Phase 3 — MIP business rules (`01_SPEC.md` §14.1) — done (2026-09-05)

`specs/0006-mip-business-rules/` (`spec.md`, `plan.md`, `tasks.md`) — all nine
tasks (`T-001`-`T-009`) done. All-or-none routes, minimum tickets, lot sizes,
and a new cardinality cap (`domain/policies.py::UtilizationPolicy.
maximum_active_routes`) are each modeled with a binary route-activation
variable (`z`) or integer lot-count variable (`n`), contributed by three new
MIP-only constraint components (`components/constraints/mip_rules.py::
RouteActivationConstraint`, `CardinalityConstraint`, `LotSizeConstraint`) on
top of every existing baseline LP component, unchanged
(`formulation/mip.py::compile_mip`). `formulation/lp.py::compile_lp` now fails
closed — raises a structured, per-field `InputValidationError` (code
`MIP_REQUIRED`) — rather than silently ignoring these fields on a request
that needs them; `InventoryOptimizer.optimize()`
(`formulation/compiler_support.py::needs_mip`) auto-routes each request to
whichever compiler it actually needs, so callers never choose manually.

Nothing in `reporting/`, `validation/`, `solvers/`, `services.py`, or `cli.py`
needed any change: T09's `HighsBackend` already handled integer variables and
suppressed duals for them, T10's `validation.solution_verifier` already
checked integrality against whatever array it was given, and T11's
attribution/explanation logic operates purely on primal values and domain
fields. `specs/engine_spec/TRACEABILITY.md`'s `LP-009` row moved `SPECIFIED` →
`IMPLEMENTED` for the MIP portion specifically (QP/PWL/NLP — §14.2-14.4 —
remain `SPECIFIED`, tagged T18 and later). 19 new tests
(`tests/golden/test_mip_business_rules.py`,
`tests/unit/test_mip_compiler.py`); zero regressions in the pre-existing 153.

### Phase 4 — QP allocation-stability penalty (`01_SPEC.md` §14.2) — done (2026-09-05)

`specs/0007-qp-allocation-stability/` (`spec.md`, `plan.md`, `tasks.md`) — all
eleven tasks (`T-001`-`T-011`) done. Of §14.2's four candidate convex terms
(squared deviation from current allocations, borrower/security concentration,
covariance-weighted risk, utilization-target deviation), only the first is
groundable today with no new domain concept — a new desk-level
`config.objective.allocation_stability_penalty` coefficient penalizes
`(q_j - current_quantity_shares_j)^2` per route, contributed entirely via the
existing `inc_j`/`dec_j` transition variables (zero at the unchanged baseline,
no new `CompiledProblem` field) by a new objective component
(`components/objective_terms/allocation_stability.py`) on top of every
existing baseline component, unchanged (`formulation/qp.py::compile_qp`).
`compile_lp` fails closed (`QP_REQUIRED`) on a positive penalty; `compile_mip`/
`compile_qp` each fail closed (`MIQP_UNSUPPORTED`) if the other's own trigger
is also present (Section 14.2: mixed-integer QP needs a separate capable
backend or an explicit decomposition, neither of which exists);
`InventoryOptimizer.optimize()` auto-routes exactly as it already does for
MIP.

**A real numerical finding shaped this spec.** Reconstructing the compiled QP
model directly against the pinned `highspy` (1.15.1) `Highs()` API — bypassing
this repo's compiler entirely — reproduced a genuine solver stall: HiGHS's QP
active-set method iterates into the millions without converging whenever the
Hessian's magnitude sits several orders below the rest of the model's
coefficients, a real backend-version limitation Section 14.2 anticipates
("Continuous QP support is backend/version capability-gated"), not a modeling
defect. Uniformly rescaling the whole objective by one positive constant (an
exact transformation — never changes the optimal `x`) resolved every
reproduced case instantly. `formulation/qp.py::compile_qp` computes this scale
factor and attaches it via the long-dormant `CompiledProblem.scaling` field
(Section 20.3, unused since Phase 0A); only `solvers/highs.py` ever reads it —
`CompiledProblem.linear_objective`/`quadratic_objective` themselves stay in
true USD units throughout, so `validation.solution_verifier`/
`reporting.attribution` needed zero scaling-awareness changes beyond
including the quadratic term in the independent objective reconstruction
(the one other real gap this spec closed: without it, every correct QP solve
would have failed verification by exactly its own quadratic magnitude).

While adding the new QP-only objective component, `formulation/
compiler_support.py::resolve_component` gained a formulation-membership
check — Section 15.1 says components "declare formulations" but nothing
enforced it before this spec; verified purely additive (every existing
component already declares its correct, complete scope). `specs/engine_spec/
TRACEABILITY.md`'s `LP-009` row extends its `IMPLEMENTED` status to cover
this QP term (PWL/NLP and QP's other three candidate terms stay `SPECIFIED`).
21 new tests (`tests/golden/test_qp_allocation_stability.py`,
`tests/unit/test_qp_compiler.py`, `tests/unit/test_qp_support.py`,
`tests/benchmark/test_qp_scale.py`); zero regressions in the pre-existing 172.

### Phase 5 — Nonlinear and multi-period research (`01_SPEC.md` §14.4, §13; `00_PLAN.md`) — item 1 done (discrete form), item 2 drafted

Two unrelated pieces. **Item 1 (joint fee/quantity pricing) is done, in its discrete form** —
`specs/0009-discrete-fee-tier-pricing/` — see below. **Item 2 (multi-period settlement and
scenario-tree extensions) is now drafted** as `specs/0010-multi-period-settlement/` (deterministic
form only — see below); before this draft, it had no domain grounding at all:
`FormulationConfig.planning_horizon_days` exists but is only a day-count scalar feeding
`fee_revenue`, not a time-indexed decision sequence, so this really is new domain modeling from
scratch, not an extension of something that already existed.

`00_PLAN.md`'s own guidance for this phase — "promote an extension only after
benchmark, convergence, and fallback behavior are documented" — is stricter
than any earlier phase's exit gate, and is why item 1 deliberately shipped the
discrete route (below) rather than a nonlinear backend.

**QuantSmith is of essentially no help here** (checked 2026-09-05, same pinned
commit): it has no NLP solver, no sequential-convex-approximation machinery,
and no scenario-tree/stochastic support. Its `solve_dp` is a deterministic
backward-induction DP whose own docstring requires "an enumerable, hashable
state space" — built for a single discretized scalar position
(`multi_period_rebalancing.py`), not thousands of continuous route quantities
across periods. `mean_variance.MeanVarianceOptimizer` is closed-form Markowitz
with no box bounds. Both are toy-scale conceptual references at best, matching
the earlier `solve_lp`/`solve_milp` verdict.

### Phase 5 item 1 — discrete fee-tier pricing (`01_SPEC.md` §12.4) — done (2026-09-07)

`specs/0009-discrete-fee-tier-pricing/` (`spec.md`, `plan.md`, `tasks.md`) — all ten tasks
(`T-001`-`T-010`) done, on branch `0009-discrete-fee-tier-pricing` (owner sign-off 2026-09-05, all
three blocking design questions resolved; implementation 2026-09-06/07).

The key finding that shaped it: **§12.4 already specifies this formulation
normatively** ("Discrete price-selection MIP": binary `z_gk` per candidate fee
tier, `sum_k z_gk <= 1`, `0 <= q_gk <= D_gk * z_gk`, objective `f_gk * q_gk`)
and it had simply never been built. §12.5 explicitly sanctions this as the
alternative to a nonlinear formulation: continuous fee creates a bilinear
`f_g * q_g` term that "belongs in an optional nonlinear formulation or a
documented sequential/piecewise approximation."

Because each candidate fee is a *constant*, the compiled model stays a **linear
MIP** — so HiGHS either proves global optimality or reports `FEASIBLE_LIMIT`,
the same honest contract Phase 3 established. A true NLP would only ever return
a local optimum, which §14.4 itself requires be labeled as such. That, plus
§14.3's stated preference ("prefer piecewise-linear approximations"), is why
this shipped the discrete route first; a `NonlinearSolverBackend` remains open
later and is listed in the spec's own follow-ups.

**What shipped:** an optional `DemandForecast.candidate_fee_rates` menu (empty by default, absent
for every existing request); `formulation/context.py` precomputes one `EvaluatedDemand` per
candidate fee (the existing, unchanged `elasticity.evaluate_demand_cap`, called once per tier
instead of once per group) and appends two new empty-when-unused variable blocks (`"t"` — one
binary tier-selection variable per candidate fee; `"w"` — one continuous per-route-per-tier
quantity variable); a new `components/constraints/fee_tiers.py::FeeTierConstraint` compiles §12.4's
three row families (`tier_select`, `tier_capacity`, `tier_split`); a new
`components/objective_terms/tier_pricing.py::TierPricingTerm` values the selected tier's fee as a
*delta* from the incumbent `route.fee_rate`, leaving the existing `fee_revenue` term untouched;
`formulation.compiler_support.needs_mip` gained one clause so a tiered request auto-routes to
`compile_mip` (and `compile_lp` fails closed) via the existing mechanisms, no new ones; and
`domain/results.py::PricingSelection` (a new, additive, defaulted `OptimizationResult.pricing`
section) discloses, per tiered demand group, the candidate menu offered, the fee selected, and the
quantity filled at it (§14.3's disclosure duty).

This also closed two things deferred elsewhere: Phase 3's item 2 (discrete rate-ladder selection, a
declared Non-Goal in `specs/0006-mip-business-rules/` for want of a fee-tier concept) and §14.1's
seventh MIP trigger ("one fee tier per demand group"). `validation/reconciliation.py`'s existing
error message ("use distinct demand groups or the discrete pricing MIP") now points at a facility
that actually exists.

Two deviations recorded, not silent: (1) per-route-per-tier quantities (`w_jk`) rather than one
group-level `q_gk` as §12.4 sketches, because §12.2 notes routes in a group can carry different
`revenue_share` — a group-level revenue coefficient would be wrong for them (AC-010's own test
pins this: two routes with different `revenue_share` in one tiered group are valued independently,
not at one blended rate). (2) the existing `demand_cap` component skips any demand group carrying
tiers (its row would otherwise cap quantity at the *incumbent* fee's demand, which is wrong the
moment a cheaper tier is selected) — a single guarded line, inert for every untiered request.

29 new tests (`tests/golden/test_fee_tier_pricing.py`, `tests/unit/test_fee_tier_compiler.py`,
`tests/unit/test_domain_contracts.py` additions, `tests/benchmark/test_fee_tier_scale.py`
`slow`-marked); 239 passed + 2 skipped (pandas absent), zero regressions in the pre-existing 220.
`specs/engine_spec/TRACEABILITY.md`'s `LP-004` row gains discrete-per-candidate-fee evidence; `LP-009`
extends its `IMPLEMENTED` status to cover Section 12.4's discrete price-selection MIP (PWL/NLP —
Section 14.3-14.4's continuous-fee case — and QP's other three candidate terms stay `SPECIFIED`).

### Phase 5 item 2 — multi-period settlement (`01_SPEC.md` §22.11) — done (2026-09-09)

`specs/0010-multi-period-settlement/` (`spec.md`, `plan.md`, `tasks.md`) — **Approved** (owner
sign-off 2026-09-07) and fully implemented, both designs, all fourteen tasks (`T-001`-`T-014`)
done. This spec originally carried three open design questions needing real owner judgment, not
just technical sign-off (see the resolution below); once resolved, the owner chose to build *both*
designs rather than pick one, sequenced.

The key finding that shaped it: §22.11 already specifies time-bucketed balance identities
(`on_loan_i,t`/`available_i,t`/`lendable_i,t`) normatively, and says the deterministic form "should
precede a fully stochastic formulation" (§22.12) — the same relationship `0009` used (V0's own
"Deferred extensions" list excludes "joint continuous optimization of fee and quantity"; `0009`
built the discrete alternative instead of the deferred thing itself). Here, V0 defers "multi-period
*stochastic* optimization" specifically — the deterministic precursor is not itself excluded.

**Resolution of the three original open questions (owner, 2026-09-07):** build both designs,
sequenced (projection first, joint LP second, sharing one set of primitives); validate a known
future `RECALL`'s notice against `LoanRoute.recall_notice_days` in V1 rather than deferring it; the
per-day discount rate is a configurable field (`MultiPeriodConfig.daily_discount_rate`), defaulting
to zero.

**Phase 1 — deterministic projection (`settlement/`; T-001-T-006; done 2026-09-07).** Period 0
stays exactly today's existing single-period solve — the only period actually decided. Periods
1..N are a mechanical, unoptimized projection of what already-known future `TradeEvent`s (a sale, a
recall, a return, already dated — the exact events §13.2 says a single-period solve ignores) do to
the already-solved book, via `settlement/project.py::project_multi_period`. Reuses
`scenarios/apply.py`'s existing per-event-type mechanics, extracted into a shared
`select_effective_events`/`apply_events` pair (all 13 of `apply_scenario`'s own pre-existing tests
kept passing unchanged through that extraction). New, additive result type
`domain/settlement.py::MultiPeriodProjection` (`mode="projected"`), mirroring
`ScenarioComparison`/`StressTestReport`'s own precedent — zero changes to `formulation/`,
`components/`, or any compiler. `validation/reconciliation.py::check_recall_notice_sufficiency`
(T-002) is shared by both designs.

**Phase 2 — joint multi-period LP (`formulation/multi_period.py`; T-007-T-010; done 2026-09-09).** A
new compiler replicates every existing baseline LP component's exact mathematical structure once
per planning period (period-suffixed `q`/`inc`/`dec`/`a` variable blocks, e.g. `"RT-A@001"`), linked
by a per-period transition identity, with the objective jointly maximizing discounted revenue
across the whole horizon — so period-0 allocation can genuinely account for a known future event
rather than merely being reported against it afterward. `formulation.compiler_support.
multi_period_conflict_issues` (T-007) fails closed if a request combines `planning_periods` with
any MIP/QP/fee-tier trigger — Phase 2's V1 is a pure continuous LP. `solve_multi_period` (T-010) is
a **new, separate entry point**, deliberately not folded into `facade.InventoryOptimizer.
optimize()`'s existing auto-routing: Phase 1's own projection *requires* `optimize()` to keep
solving period 0 alone, ignoring `planning_periods` entirely, since that period-0-only result is
its own input — auto-routing a multi-period request away from `optimize()` would silently break
Phase 1. `facade.py` itself is untouched by this spec.

Two implementation-level decisions surfaced only once code was written and are recorded, not
picked silently (`plan.md`'s "Deviations Discovered During Implementation"): (1) `RETURN` (a
borrower's voluntary return) lowers both a route's `maximum_quantity_shares` and
`hard_minimum_quantity_shares` by the returned quantity, unlike `RECALL` (a lender's contractual
pull), which lowers only the max, floored at the *unchanged* minimum — `plan.md`'s own text draws
this distinction; (2) an already-ineligible route's upper bound at period `t >= 1` clamps to its
own period-0 baseline `current_quantity_shares`, since there is no period-`(t-1)` scalar to clamp
against once quantity becomes a free decision variable at later periods — no known future event
ever makes a route newly ineligible, so this only matters for a route that started that way.

**What's genuinely still open, not silently dropped (T-011-T-013; done 2026-09-09/11):** 20 new
Phase 2 tests (`tests/golden/test_multi_period_lp.py`, `tests/unit/
test_multi_period_lp_compiler.py`, on top of Phase 1's 15) plus a `slow`-marked scale benchmark
(`tests/benchmark/test_multi_period_lp_scale.py`, RISK-004's route×period growth); 275 passed, 2
skipped total, zero regressions. `specs/engine_spec/TRACEABILITY.md` gained a new `MPS` prefix and
three rows (`MPS-001`-`MPS-003`), all `IMPLEMENTED` — no existing row covered §22.11/§22.12 before
this spec.

**Explicitly deferred, per the spec's own Non-Goals, not forgotten:**
- **§22.12's stochastic/scenario-tree extension** (chance constraints, CVaR, probability-weighted
  scenarios) — entirely untouched; `00_PLAN.md`'s own deferred-extensions list already excludes
  this, and §22.11 itself says the deterministic form should come first.
- **MIP/QP business rules combined with the joint multi-period LP** — deferred (the joint LP's V1
  fails closed on any such combination); no desk need identified yet.
- A real business-day/holiday calendar (no calendar port exists anywhere in this repo; every
  `planning_periods` date is treated as a valid settlement day for V1), corporate-action deltas,
  time-varying fee rates/prices within the horizon, and a CLI subcommand (library function only,
  matching how `run_stress_test` shipped in `specs/0004-scenario-engine/`).

After Phase 5: the Bloomberg-enriched realism workstream and the agency/prime
desk workstream — see `00_PLAN.md` for exit gates on each.

### Tabular result output (`01_SPEC.md` §7/§7.1) — done (2026-09-06)

`specs/0008-tabular-result-output/` (`spec.md`, `plan.md`, `tasks.md`) — all
twelve tasks (`T-001`-`T-012`) done. Closes two surfaces §7's own package tree
names but this repo never built: `reporting/tables.py` ("reporting owns
tables, attribution, serialization" per §7.1 — T11 built attribution and, via
Pydantic, serialization; tables were skipped) and a new `adapters/` layer
("JSON and optional dataframe conversion"). `reporting/tables.py` projects
`OptimizationResult`/`ScenarioComparison`/`StressTestReport` into thirteen
named, column-contracted tables (documented in `plan.md`'s "Table catalogue"
and in `README.md`'s new "Tabular output" section) — pure, dependency-free,
recomputing nothing. `adapters/csv_io.py` writes them with the standard
library only; `adapters/dataframe.py` is the sole module in the package
allowed to import `pandas`, lazily, raising `ConfigurationError` (naming the
extra) when it is absent — mirroring how `solvers/highs.py` already owns the
optional `highspy` import. A new `inventory-optimizer tables --input
result.json --output-dir DIR [--kind result|scenarios|stress]
[--run-summary-layout wide|long]` subcommand ties it together, composing with
`optimize`/`scenarios` rather than changing either.

**A real defect surfaced while building this, fixed in the same pass**:
`OptimizationResult` could not round-trip its own JSON —
`ConstraintActivity.lower` (E1's `demand_cap` rows are one-sided, `-inf`)
serializes to `null`, which a plain `float` field then rejected on read-back.
Nothing had ever read a result back before `tables --input` did; `optimize
--output result.json` had always written a file the package itself couldn't
parse. Fixed with two `BeforeValidator` type aliases in `domain/results.py`
mapping `null` back to `-inf`/`+inf` on `ConstraintActivity` and
`VerificationSection`'s violation fields — emitted JSON is byte-identical,
only reading is repaired, and a regression test pins it
(`test_result_builder.py::test_result_round_trips_through_its_own_json`).

`pyproject.toml`'s `dataframe` extra (`pandas>=2.2`, declared since Phase 0A
with zero usage until now) has its first real consumer; `pandas` is still not
installed in this `.venv`, so its own tests skip cleanly via
`pytest.importorskip` while the CSV path (which needs no extra) is fully
exercised. `specs/engine_spec/TRACEABILITY.md`'s `ARC-004` row gains partial
evidence (`tests/unit/test_architecture_boundaries.py` proves the `adapters`
layer's own boundary; the full pairwise layer matrix stays a follow-up). 29
new tests; 220 passed + 2 skipped (pandas absent), zero regressions in the
pre-existing 193.

Explicitly *not* built, each recorded with reasoning: charts, dashboards,
Excel workbooks (the QuantSmith dashboard surfaces were already evaluated and
parked — see below), narrative prose summaries, any new derived metric, and a
redundant `json_io.py` wrapper around what Pydantic already does.

### Possible spec idea: schedules/collateral (T29-T32) via DocumentRefinery — not scoped, not started

`SCH-001`–`SCH-004` (T29, schedule resolution) and `COL-001`–`COL-004`
(T30-T32, collateral) are entirely `SPECIFIED`, zero code — see the phase
audit above. Both need a real source of eligibility/collateral schedule data
(§9.6: `EligibilityRule`, `CollateralSchedule`), and this repo has no adapter
or ingestion path for that today; a schedule/collateral spec would otherwise
have to invent one from scratch alongside the optimizer-side compiler work.

A sibling, same-owner repository —
**[DocumentRefinery](../../../agentic_systems/DocumentRefinery/)** (a local
sibling-directory path specific to this machine's current layout, not a
portable URL — see `document_refinery_handoff.md` there for its own full
context) — already exists to solve exactly the upstream half of this problem:
it ingests collateral/CSA/repo/fee-schedule
documents and lands clause-level-lineage, bitemporal gold tables. Its Tier-1
document scope names, verbatim, "Collateral eligibility schedules (tri-party
and bilateral), concentration limits" and "CSAs and credit support annex
amendments (eligibility, haircuts, thresholds, MTA, currencies)" —
`01_SPEC.md` §9.6's `CollateralSchedule` fields (haircut buckets, margin
factor, concentration limits, currency scope, minimum transfer amount) map
closely onto its `gold_eligibility_terms` columns (`haircut_pct`,
`concentration_limit_pct`, `concentration_basis`, `currency_scope`,
`rating_floor`, `tenor_cap_days`, `asset_criterion`, `eligible`).

**This is an idea, not a plan — real gaps before it's buildable:**

- DocumentRefinery's own Phase 1 (the one working vertical slice, "collateral
  eligibility schedules") is **owner-acceptance-pending**, not production:
  ≥95% field accuracy and ≤15-minute review time are unmeasured per its own
  handoff. CSA terms and lending-fee schedules — the pieces closest to
  `01_SPEC.md`'s fee/term schedule needs — are its own **Phase 4, "not
  started."** GMRA/MRA/MSLA (repo & securities-lending terms) are Tier-1
  *scope*, not yet a built pipeline either.
- Its `eligible BOOLEAN` + haircut/concentration columns are not a drop-in
  match for §9.6's five-way `ALLOW`/`DENY`/`GRANDFATHER`/`RECALL_ONLY`/
  `REVIEW` action — a translation layer would be needed, not a type cast.
- Architecturally this must land as an **adapter, not a core dependency** —
  the same boundary `ARC-002` already draws around QR Haven/vendor clients
  (`inventory_optimizer`'s core must not import a document-ingestion
  package); a real spec would define a small ingestion adapter (in either
  repo) translating DocumentRefinery's gold tables into `EligibilitySchedule`/
  `CollateralSchedule` domain objects, not a direct import.
- Being same-owner is a real advantage (no external-vendor trust/versioning
  question, unlike QuantSmith) but doesn't change the maturity gap above.

Worth a real look once T29/T30-T32 are actually being scoped — and worth
checking DocumentRefinery's own progress at that time, since both repos are
independently active. Not something to start now.

## Using QuantSmith to build the rest of this repo

Two layers were adopted (see "What this repo is"); both have concrete uses here,
beyond just the constitution/gates already wired into CI.

### The agents (scaffold) — routes almost 1:1 onto the task list above

| Next task | QuantSmith agent |
| --- | --- |
| T11 (done) — shadow prices, solver diagnostics, reason codes | `agents/optimization/solver_diagnostics_sensitivity/` |
| T12 (done), T13-T14 (done), Phase 3 (done), Phase 4 (done) / later phases — turning an ambiguous next decision into variables/constraints/ACs before coding | `agents/optimization/problem_formulation/` |
| Phase 3 (done) — MIP business rules (lot sizes, all-or-none, cardinality) | `agents/optimization/mixed_integer_optimization/` |
| Phase 5 (done) — nonlinear/multi-period research | `agents/optimization/problem_formulation/`, `agents/optimization/linear_programming/` for the reused baseline |
| Collateral workstream (T30-T32: haircuts, capacity, joint mode) | `agents/optimization/collateral_margin_optimization/` — named for exactly this problem |
| General LP review as more constraint components get added | `agents/optimization/linear_programming/` |
| Routing the above as work grows | `agents/optimization/optimization_orchestrator/` |
| Writing/keeping the tests that back each new AC | `agents/testing_validation/` |
| Driving each new task through Specify → Plan → Tasks → Implement → Verify → Operate | `agents/workflow_orchestrator/` — invoke this one first; it routes to the rest |

`agents/optimization/inventory_supply_chain/` also exists but is a false-friend
match — it's aimed at physical-goods inventory (safety stock, multi-echelon
replenishment), not securities-lending inventory. Don't route there.

### The `quantsmith` package (the `agentic` extra)

Narrower fit, since `inventory_optimizer` already has its own purpose-built
HiGHS/`CompiledProblem` stack — not a replacement for it. Verified concretely
(2026-09-05) by reading the installed package's own source
(`.venv/lib/python*/site-packages/quantsmith/`, pinned commit
`3951654f56c995465b4c090f39eeb34f8c9671ff`):

- **CLI pattern (already used for T12):** skip `quantsmith-sec-lending`'s CLI
  (`quantsmith.quant.agentic_quant.cli.sec_lending`) — it's a single-command
  `argparse` demo with no subcommands and no structured error handling.
  `quantsmith-memory`'s CLI (`quantsmith.pipelines.workflow_memory_cli`) is
  the right template for a multi-verb CLI: `add_subparsers` + one `_cmd_*`
  handler per verb + a `dispatch` dict + `main(argv) -> int`, with recognized
  exceptions caught and reported to stderr rather than raised raw. `cli.py`
  mirrors this convention.
- `quantsmith.pipelines.optimization_solvers.solve_lp` / `solve_milp` as an
  independent reference solver to cross-check results against: real, but
  pure-Python, dense, and `x >= 0`-only (no arbitrary variable bounds, no
  sparse matrices, no quadratic-objective support) — usable only as a toy
  oracle for small LP/MIP test fixtures via translation glue (densify, split
  ranged rows, encode bounds as extra rows), not a production cross-check
  against our `CompiledProblem`'s sparse/ranged-row/arbitrary-bounds/QP shape.
  Not used for Phase 4's QP work (no QP support in `quantsmith` itself); the
  cross-check that mattered there was empirical (reconstructing the compiled
  model directly against raw `highspy` calls — see Phase 4's writeup above).
- `quantsmith.pipelines.DashboardSpec` / `render_streamlit` / `write_xlsx`:
  **weaker fit than it looked.** These are metadata-only — a `Panel`
  references a *named* metric/dataset resolved by a live data-serving
  endpoint at render time (`render_streamlit`'s generated app calls
  `pd.read_json(f'{endpoint}?dataset=...')`); `write_xlsx` doesn't even
  accept a `DashboardSpec` (it takes a separate `ExcelWorkbookPayload` and
  only writes a header row). Feeding `OptimizationResult`'s actual nested
  values into this pattern needs real reshaping (flatten sections into rows,
  define governed metric names, stand up a data-serving layer), not glue
  code — parked, not adopted.

### How to actually start

**T11, T12, T13-T14, the §24 test-hardening pass, Phase 3 (MIP business
rules), Phase 4 (QP allocation-stability), the tabular result output spec,
Phase 5 item 1 (discrete fee-tier pricing), and Phase 5 item 2 (multi-period
settlement, both designs) are all done** (2026-09-04, 2026-09-05 ×5,
2026-09-06, 2026-09-07, 2026-09-09) — see above. All of it is merged to
`main` on GitHub (`thatquantguy44/InventoryBallast` — see "Open items" below;
the remote no longer needs creating).

**Next up: nothing in the engine spec's own phase sequence is scoped yet.**
Per `00_PLAN.md`, after Phase 5 the two remaining workstreams are the
Bloomberg-enriched realism track (§22, `DAT-*` rows, all `SPECIFIED`) and the
agency/prime desk track (§23, `AGY-*`/`PRM-*` rows, all `SPECIFIED`) — neither
has a `specs/NNNN-*` directory yet. The "Possible spec idea: schedules/
collateral (T29-T32) via DocumentRefinery" section above is the most
concretely scoped candidate among them, but is explicitly flagged as an idea,
not a plan, pending DocumentRefinery's own Phase 4 (CSA/lending-fee schedules)
maturing. Bring a real desk need to the owner before starting any of these —
none has the kind of "spec already says exactly what to build" grounding that
made `0009`/`0010` straightforward once approved.

**Also worth doing, lower stakes than a new phase:** `docs/adoption_guide.md`
step 6 was finally wired in this repo (`.githooks/`, `setup-hooks.sh`, a
Claude Code `SessionStart` hook) — see "Open items" below for the real gap
this closed and the one it didn't.

## Open items for the next agent (not yet resolved)

- **GitHub remote: exists now.** `thatquantguy44/InventoryBallast`, created around 2026-09-09.
  `main` has real history via merged PRs (#1 Phase 1, #2 a docs rename, #3-#4 Phase 2, #5 the git
  hooks below); CI runs for real on every push/PR.
- **`quantsmith` pin:** `requirements.txt` and `pyproject.toml`'s `agentic` extra
  pin `quantsmith @ git+...@3951654f56c995465b4c090f39eeb34f8c9671ff` — the exact
  `origin/main` commit at adoption time, because QuantSmith has no tagged release
  yet. Re-pin to a tag once one exists.
- **CI runs for real now — and it caught a real gap.** `.github/workflows/ci.yml`'s `gates` job
  (spec/spec-index/agent-catalog/pipeline-contract/secret-scan/`agent-attribution`, all
  `QF_STAGE_ENFORCE=1`) and `tests` job both run on every push/PR. The `tests` job has been green
  throughout. **The `agent-attribution` check failed on PRs #3 and #4** — a remote agent session's
  own git identity was `Claude <noreply@anthropic.com>` (the execution environment's default, not
  something anyone configured on purpose), and both PRs were merged by the owner despite the
  failing check (i.e. `gates` is not currently a *required* status check in branch protection — it
  reports, it doesn't block). **`main` now permanently carries 5 commits with this bad identity**
  (all of spec 0010 Phase 2's own commits: T-008 through T-013) — rewriting them would mean
  rewriting `main` itself, a materially bigger operation than anything attempted so far, and
  deliberately not done without a separate, explicit decision to do it. This is a known, disclosed
  wart in `main`'s own history, not a hidden one.
- **Local Git hooks: now wired (2026-09-11), closing half the gap above.** Per
  `docs/adoption_guide.md` step 6 in the QuantSmith SDK repo ("wire the gates into your own hooks,
  skip `.githooks/`" — the SDK's own `.githooks/`/`setup-hooks.sh` enforce SDK-repo invariants, not
  this repo's), this repo now has its own `.githooks/{pre-commit,commit-msg,pre-push}` +
  `setup-hooks.sh` (root), verified live to actually refuse a commit/push under an AI-agent
  identity rather than only reporting it after the fact in CI. A Claude Code `SessionStart` hook
  (`.claude/hooks/session-start.sh`, registered in `.claude/settings.json`) runs `setup-hooks.sh`
  automatically on every remote session, plus recreates `.venv` and installs the dev/highs extras
  so `pytest`/`ruff`/`mypy` work immediately — closing the actual gap that let the bad-identity
  commits happen in the first place (nothing wired hooks for a fresh checkout). **This only
  prevents *future* recurrence**, and only once merged to `main`'s default branch (a `SessionStart`
  hook has no effect until then) — it does not retroactively fix the 5 commits above.
- **Branch protection: not evaluated.** Whether `gates` should become a *required* status check
  (so a red run can't be merged past at all, closing the other half of the gap) is a GitHub
  repo-settings decision for the owner, not made in this session.
- **`specs/engine_spec/` cross-references:** the 6,500-line spec set was copied
  verbatim from `QR-Haven` and still describes some things in monorepo terms
  (e.g. "the parent repository", the `qr_haven` platform adapter living
  elsewhere) — that's accurate (the adapter genuinely stays in `QR-Haven`), but
  worth a read-through pass if the spec set itself needs updating for the
  standalone repo's own docs conventions.
