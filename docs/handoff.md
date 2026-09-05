# Handoff

The roadmap a new owner (human or agent) reads first. Keep this in sync: a new
`specs/NNNN-*` directory should land with an edit here (enforced by the
`handoff-sync` gate).

## What this repo is

InventoryBallast is a portable, solver-neutral securities-lending inventory
optimization engine. It was extracted (2026-09-04) from the `QR-Haven` monorepo's
`projects/inventory_optimizer/` into its own repository, preserving that
directory's original 6 commits via `git subtree split`. It is not yet pushed to a
GitHub remote — it exists as a local repo only, by the owner's choice at
extraction time.

It also adopts the [QuantSmith](https://github.com/joshualutkemuller/QuantSmith)
agentic scaffold (`instructions/`, `hooks/`, `agents/`, `prompts/`, `templates/`,
`CLAUDE.md`) and pins the `quantsmith` package as an optional dependency. See
`CLAUDE.md` for the operating model and `docs/adoption_guide.md`-equivalent
guidance lives in the QuantSmith repo itself (not copied here — see "Open items"
below).

## The actual spec: `specs/spec002/`

The engine's normative specification is [`specs/spec002/`](../specs/spec002/) —
copied over from `QR-Haven` in the same extraction (it was **not** carried by the
`git subtree split`, since it lived outside `projects/inventory_optimizer/` in the
monorepo; it was copied separately and is new, uncommitted-by-QuantSmith content
specific to this engine, not the QuantSmith reference spec). Read in this order,
per `specs/spec002/00_PLAN.md`'s own "Handoff Order":

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

## Current state (verified 2026-09-05)

Per `specs/spec002/00_PLAN.md`'s status line and `TRACEABILITY.md`:

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
  `formulation/compiler_support.py`; `specs/0006-mip-business-rules/`), and T18's
  Phase 4 QP allocation-stability penalty (`formulation/qp.py::compile_qp`,
  `components/objective_terms/allocation_stability.py`,
  `formulation/qp_support.py`; `specs/0007-qp-allocation-stability/`). 193 tests
  pass in the default `pytest tests/ -q` run (with the `highs` extra installed),
  plus a real `pip install -e .` console script (`inventory-optimizer`, including
  a working `scenarios` subcommand) and two `slow`-marked benchmark smoke tests
  (Core-desk-scale LP from `specs/0005-test-hardening/`; moderate-scale QP from
  `specs/0007-qp-allocation-stability/`) run separately.
- **Test coverage hardened against `01_SPEC.md` §24 (2026-09-05):** an audit
  against the normative "Testing Strategy" section found `hypothesis` (a pinned
  dev dependency since T01) had never actually been used; `specs/0005-test-
  hardening/` closes that and four other real gaps — see its entry below.
- **Not yet started:** Phase 5 (nonlinear/multi-period research; `01_SPEC.md`
  §14.4, §13's multi-period extensions) — see "Next priorities" below.

## Environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,highs,dataframe,agentic]"
.venv/bin/python -m pytest tests/ -q         # 193 passed, as of this writing (fast; excludes `slow`)
.venv/bin/python -m pytest tests/ -m slow -q # 2 benchmark smoke tests (Core desk LP + QP scale, ~1-2s)
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

`specs/spec002/TRACEABILITY.md` rows `LP-007`, `VER-001`, `VER-002`,
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

`specs/spec002/TRACEABILITY.md`'s `PLT-002` row gained an evidence pointer to
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
§13's own text, so it carries no `specs/spec002/TRACEABILITY.md` row of its
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
**not** implemented — `specs/spec002/TRACEABILITY.md`'s `SCN-004` row stays
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
  `specs/spec002/TRACEABILITY.md`'s `LP-002` evidence.
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
fields. `specs/spec002/TRACEABILITY.md`'s `LP-009` row moved `SPECIFIED` →
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
component already declares its correct, complete scope). `specs/spec002/
TRACEABILITY.md`'s `LP-009` row extends its `IMPLEMENTED` status to cover
this QP term (PWL/NLP and QP's other three candidate terms stay `SPECIFIED`).
21 new tests (`tests/golden/test_qp_allocation_stability.py`,
`tests/unit/test_qp_compiler.py`, `tests/unit/test_qp_support.py`,
`tests/benchmark/test_qp_scale.py`); zero regressions in the pre-existing 172.

### Phase 5 — Nonlinear and multi-period research (`01_SPEC.md` §14.4, §13; `00_PLAN.md`) — next up

Not started. Joint fee/quantity demand curves through an optional nonlinear
backend or sequential convex approximation; multi-period settlement and
scenario-tree extensions. `00_PLAN.md`'s own guidance: "promote an extension
only after benchmark, convergence, and fallback behavior are documented." This
is also what the `quantsmith.pipelines.optimization_solvers.solve_milp`
reference solver (see "The `quantsmith` package" below) could become useful
for as an independent toy-scale cross-check during design review, for any
MIQP-relaxation approach to a discrete piece of this phase.

After Phase 5: the Bloomberg-enriched realism workstream and the agency/prime
desk workstream — see `00_PLAN.md` for exit gates on each.

## Using QuantSmith to build the rest of this repo

Two layers were adopted (see "What this repo is"); both have concrete uses here,
beyond just the constitution/gates already wired into CI.

### The agents (scaffold) — routes almost 1:1 onto the task list above

| Next task | QuantSmith agent |
| --- | --- |
| T11 (done) — shadow prices, solver diagnostics, reason codes | `agents/optimization/solver_diagnostics_sensitivity/` |
| T12 (done), T13-T14 (done), Phase 3 (done), Phase 4 (done) / later phases — turning an ambiguous next decision into variables/constraints/ACs before coding | `agents/optimization/problem_formulation/` |
| Phase 3 (done) — MIP business rules (lot sizes, all-or-none, cardinality) | `agents/optimization/mixed_integer_optimization/` |
| Phase 5 (next up) — nonlinear/multi-period research | `agents/optimization/problem_formulation/`, `agents/optimization/linear_programming/` for the reused baseline |
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
rules), and Phase 4 (QP allocation-stability) are all done** (2026-09-04,
2026-09-05 ×5) — see above. Repeat the same "write the spec first" pattern
for Phase 5 (nonlinear/multi-period research) next: invoke
`workflow_orchestrator`, let it route to `agents/optimization/
problem_formulation/` (and `linear_programming/` for the reused baseline
components) for turning §14.4's nonlinear-backend/sequential-convex-
approximation requirements and §13's multi-period extensions into `REQ-*`/
`AC-*` rows and `testing_validation` for the AC tests, and write a real
`specs/0008-*` directory (`0007` is now taken by
`specs/0007-qp-allocation-stability/`) tracked by the same `spec`/
`spec-index` gates the specs before it used. `00_PLAN.md`'s own Phase 5
guidance — "promote an extension only after benchmark, convergence, and
fallback behavior are documented" — is stricter than any prior phase's exit
gate; budget real design-review time before implementation starts.

## Open items for the next agent (not yet resolved)

- **GitHub remote:** none yet. Local commits only. Create when the owner asks.
- **`quantsmith` pin:** `requirements.txt` and `pyproject.toml`'s `agentic` extra
  pin `quantsmith @ git+...@3951654f56c995465b4c090f39eeb34f8c9671ff` — the exact
  `origin/main` commit at adoption time, because QuantSmith has no tagged release
  yet. Re-pin to a tag once one exists.
- **CI not yet run for real:** `.github/workflows/ci.yml` was added and its gate
  commands were dry-run locally (`sh hooks/stages/run-stage.sh ...`, all passing),
  but it has never executed on actual GitHub Actions since there's no remote yet.
  Verify green on first push.
- **Attribution policy: adopted and enforced.** `CLAUDE.md`'s "GitHub posts"
  section says to omit AI attribution footers unconditionally, and CI's `gates`
  job now runs `hooks/stages/agent-attribution-check.sh` **enforced**
  (`QF_STAGE_ENFORCE=1`) — it fails the build if a commit carries an AI
  author/co-author. The commit history was rewritten (`git filter-branch
  --msg-filter`, local-only, never pushed) to strip the `Co-Authored-By: Claude
  Sonnet 5` trailers that earlier commits had; author/committer identity on
  every commit was already the repo owner's own, so only the trailers needed
  removing. Any agent committing here going forward must not add one.
- **`specs/spec002/` cross-references:** the 6,500-line spec set was copied
  verbatim from `QR-Haven` and still describes some things in monorepo terms
  (e.g. "the parent repository", the `qr_haven` platform adapter living
  elsewhere) — that's accurate (the adapter genuinely stays in `QR-Haven`), but
  worth a read-through pass if the spec set itself needs updating for the
  standalone repo's own docs conventions.
