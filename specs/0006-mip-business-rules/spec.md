# Spec: MIP business rules (Phase 3)

- **ID:** 0006-mip-business-rules
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted and implemented by Claude Code)
- **Approver:** Joshua Lutkemuller, CFA ("Build this out" — approved proceeding with Phase 3 as the next priority identified at the close of `0005-test-hardening/`)
- **Last updated:** 2026-09-05

> WHAT and WHY only. No implementation detail — that belongs in `plan.md`.

## Problem & Context

`specs/engine_spec/01_SPEC.md` §14.1 ("MIP triggers") and `00_PLAN.md`'s Phase 3 ("MIP business
rules") define discrete decision requirements the baseline continuous LP (T08) cannot represent:
all-or-none fill, minimum active ticket, integer lot multiples, fixed route activation cost,
maximum active route count (cardinality), mutual exclusion, and one-fee-tier-per-demand-group
(discrete rate-ladder selection). `00_PLAN.md`'s own exit gate: "integrality is verified after
solve; a time-limited incumbent is never labeled optimal."

Three of §14.1's seven triggers are **already declared on `domain.loans.LoanRoute`** (T04, Phase
0A) but **wired nowhere** — `all_or_none: bool`, `lot_size_shares: float | None`, and
`minimum_active_quantity_shares: float | None` all exist and validate correctly at construction
time, but `formulation.lp.compile_lp` never reads any of them. A route with `all_or_none=True`
today silently compiles as an ordinary continuous route — the exact "silently ignores a hard
requirement" failure mode constitution P4 exists to prevent. This spec closes that gap for real,
rather than leaving it as a latent inconsistency between the domain contract's promise and the
compiler's behavior.

Much of the surrounding MIP *infrastructure* already exists and needs no new work: `HighsBackend`
already declares `Capability.MIP` and sets `problem.integrality`-aware HiGHS options
(`solvers/highs.py`); `SolverConfig.time_limit_seconds`/`relative_gap` already exist and are
already wired into `HighsBackend._apply_options`; the status mapper already distinguishes
`FEASIBLE_LIMIT` from `OPTIMAL` for a time-limited incumbent (`tests/unit/
test_highs_backend.py::test_time_limit_with_feasible_incumbent_is_feasible_limit`, already
passing); and `validation.solution_verifier.verify_solution` already computes
`max_integrality_violation` against whatever `CompiledProblem.integrality` array it is given
(`tests/unit/test_solution_verifier.py::test_integrality_violation_is_caught`, already passing,
using a synthetically-flagged array). **What's missing is the formulation layer**: nothing
compiles real binary/integer variables from `LoanRoute`'s own fields, so none of this
already-correct downstream machinery has ever been exercised end to end.

`00_PLAN.md`'s Phase 3 scope is narrower than all of §14.1: item 2 ("discrete rate-ladder
selection") and "fixed route activation cost"/"mutual exclusion" have no grounding anywhere in
this repo (no domain field, no worked example) — this spec builds the four triggers that *are*
grounded (three existing fields plus cardinality, which needs one small, low-risk field addition)
and defers the rest, the same way every prior phase in this repo has scoped itself to what's
actually buildable rather than everything a section names. `01_SPEC.md` §14.2-§14.4 (QP,
piecewise-linear, nonlinear) are separately later phases (Phase 4-5) and out of scope entirely.

**No `EXAMPLES.md` worked case exists for any MIP scenario** (E1-E9 are all continuous-LP,
elasticity, scenario, schedule, collateral, agency/prime, or infeasibility cases) — this spec's
golden fixtures are hand-constructed and reasoned through explicitly in `plan.md`, the same
approach `specs/0005-test-hardening/` used for its two ungrounded golden cases.

## Goals

- Wire `LoanRoute.all_or_none` into a real activation constraint: the route's quantity is either
  zero or exactly its `maximum_quantity_shares`.
- Wire `LoanRoute.minimum_active_quantity_shares` into a real activation constraint: the route's
  quantity is either zero or between its minimum ticket and maximum.
- Wire `LoanRoute.lot_size_shares` into a real integer-lot constraint: the route's quantity is an
  integer multiple of its lot size.
- Add cardinality (§14.1's "maximum active route count"): one new field,
  `UtilizationPolicy.maximum_active_routes`, limiting how many routes in its scope may be active
  (quantity > 0) simultaneously.
- A new `formulation.mip.compile_mip(request, config) -> CompiledProblem` that reuses every
  already-implemented baseline constraint/objective component (inventory balance, transition
  identity, demand cap, utilization cap, reserve buffer, counterparty limit, fee revenue,
  transition cost) unchanged, adding only the new MIP-specific components on top.
- `formulation.lp.compile_lp` (continuous) shall **reject**, not silently ignore, a request that
  needs any of the above — fail closed rather than under-deliver a hard requirement.
- `facade.InventoryOptimizer.optimize()` shall route to `compile_mip` automatically whenever a
  request needs it, with no caller action required.
- Golden tests proving each trigger works end to end (compile → solve → verify → result), plus one
  proving the verifier genuinely catches an integrality violation from a *real* compiled MIP (not
  only the existing synthetic-corruption test).

## Non-Goals

- **Fixed route activation cost** — needs a new `LoanRoute` field with no grounding (no worked
  example, no existing field) and its own new objective-term component. Deferred pending a real
  need.
- **Discrete rate-ladder selection** ("one fee tier per demand group", `00_PLAN.md` Phase 3 item
  2) — needs a wholly new domain concept (a set of candidate fee tiers per demand group). Deferred;
  no existing field or example grounds its shape.
- **Mutual exclusion** (as its own named feature, beyond what cardinality already provides) — §14.1
  lists it alongside cardinality but gives no separate worked mechanic; a `maximum_active_routes=1`
  cardinality policy already expresses simple mutual exclusion. A richer "these specific routes are
  mutually exclusive" pairing concept is deferred.
- **§14.2 Convex QP, §14.3 piecewise-linear, §14.4 nonlinear extensions** — `00_PLAN.md`'s own
  Phase 4/5, not Phase 3. Untouched.
- **Combining multiple MIP triggers on the same route in the golden tests** — each trigger is
  tested in isolation (separate routes/fixtures). The constraints compose mathematically without
  special-case code when combined (see `plan.md`), but this spec does not add a dedicated
  combined-trigger golden test — tracked as a follow-up.
- **A new console-script surface** for MIP-specific options (e.g. exposing `relative_gap` as its
  own CLI flag) — `cli.py`'s `optimize`/`scenarios` subcommands already thread the resolved config
  (including `SolverConfig.relative_gap`/`time_limit_seconds`) through unchanged; no new flag is
  added.

## Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| REQ-001 | The system shall add a new constraint component compiling `q_j = maximum_quantity_shares_j * z_j` (with `z_j` a new binary variable) for every route with `all_or_none=True`. | must |
| REQ-002 | The system shall add a new constraint component compiling `min_ticket_j * z_j <= q_j <= maximum_quantity_shares_j * z_j` (reusing the same `z_j` if a route also qualifies under REQ-001, else a fresh one) for every route with `minimum_active_quantity_shares` set. | must |
| REQ-003 | The system shall add a new constraint component compiling `q_j = lot_size_j * n_j`, `0 <= n_j <= floor(maximum_quantity_shares_j / lot_size_j)` (with `n_j` a new non-negative integer variable) for every route with `lot_size_shares` set. | must |
| REQ-004 | The system shall add `domain.policies.UtilizationPolicy.maximum_active_routes: int \| None`, and a new constraint component compiling `q_j <= maximum_quantity_shares_j * z_j` for every route in a policy's scope (reusing `z_j` from REQ-001/002 where applicable) plus one row `sum(z_j) <= maximum_active_routes`. | must |
| REQ-005 | The system shall provide `formulation.mip.compile_mip(request, config) -> CompiledProblem`, composing the existing `REQUIRED_CONSTRAINTS`/`REQUIRED_OBJECTIVES` baseline components unchanged plus the new components from REQ-001 through REQ-004, and setting `CompiledProblem.integrality` correctly for every `z`/`n` variable. | must |
| REQ-006 | `formulation.lp.compile_lp` shall raise a structured `InputValidationError` (naming the offending route or policy and which MIP trigger it needs) rather than silently compiling a request that has any route with `all_or_none=True`, `lot_size_shares` set, or `minimum_active_quantity_shares` set, or any `UtilizationPolicy` with `maximum_active_routes` set. | must |
| REQ-007 | `facade.InventoryOptimizer.optimize()` shall detect whether a request needs MIP treatment (per REQ-006's same criteria) and call `compile_mip` instead of `compile_lp` automatically, requiring no caller action. | must |
| REQ-008 | The system shall provide golden tests for each of REQ-001 through REQ-004 proving the correct discrete outcome (e.g. all-or-none never returns a partial fill; lot size never returns a non-multiple quantity), each with `verification.passed is True` and `max_integrality_violation` at zero. | must |
| REQ-009 | The system shall provide a golden test in which a real compiled MIP's primal is deliberately corrupted to a non-integer value and confirm `verify_solution` catches it (REQ-005's `integrality` array exercised end to end, complementing the existing synthetic-array test in `tests/unit/test_solution_verifier.py`). | must |

## Non-Functional Requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | No behavior change for LP-only requests | Every existing test that calls `compile_lp` on a request with no MIP-triggering field continues to pass unchanged — `build_context`'s variable index gains `z`/`n` blocks that are empty (contribute zero variables/columns) whenever no route/policy qualifies. |
| NFR-002 | Fail closed, not silently under-deliver | REQ-006's rejection is exact and complete: `compile_lp` must reject every one of the four trigger conditions, not a subset. |
| NFR-003 | No MIP shadow prices | `reporting.shadow_prices.build_shadow_prices` (T11, unchanged) already guards on `SolverResult.dual is None`, which `HighsBackend` already sets whenever `problem.integrality` has any nonzero entry — this spec adds a golden test confirming that guard actually fires for a *real* compiled MIP, not just the guard's own unit test. |

## Acceptance Criteria

| ID | Given / When / Then | Covers |
| --- | --- | --- |
| AC-001 | Given a route with `all_or_none=True`, `maximum_quantity_shares=50`, positive economics, and ample demand/inventory, when solved via the facade, then its post-quantity is `50` or `0`, never a partial value. | REQ-001, REQ-005, REQ-007 |
| AC-002 | Given a route with `minimum_active_quantity_shares=20`, `maximum_quantity_shares=80`, when solved with just enough inventory to make partial activation attractive, then its post-quantity is `0` or `>= 20`, never in `(0, 20)`. | REQ-002, REQ-005, REQ-007 |
| AC-003 | Given a route with `lot_size_shares=15`, `maximum_quantity_shares=100`, when solved, then its post-quantity is an exact integer multiple of `15` (i.e. one of `0, 15, 30, ..., 90`). | REQ-003, REQ-005, REQ-007 |
| AC-004 | Given three routes on one inventory pool under a `UtilizationPolicy` with `maximum_active_routes=2`, all with positive, distinct economics, when solved, then exactly two routes have a positive post-quantity and one is exactly zero — the route excluded is not the one with the worst economics if excluding it would violate inventory or demand feasibility (i.e. the solver optimizes the *set* of two, not greedily by fee rank alone). | REQ-004, REQ-005, REQ-007 |
| AC-005 | Given any request with no MIP-triggering route or policy, when compiled via `compile_lp` directly, then it compiles exactly as before (same variable/row counts as pre-this-spec) — the existing E1/E2/E3 golden tests continue to pass unchanged. | NFR-001 |
| AC-006 | Given a request with an `all_or_none` route, when compiled via `compile_lp` directly (not through the facade), then it raises `InputValidationError` naming the route and the trigger, rather than silently ignoring `all_or_none`. | REQ-006, NFR-002 |
| AC-007 | Given the same request, when solved via `InventoryOptimizer.optimize()`, then it succeeds (routed to `compile_mip` automatically, no caller action). | REQ-007 |
| AC-008 | Given a real MIP solve from AC-003's lot-size fixture, when the returned primal's lot-count variable is corrupted to a non-integer value and passed to `verify_solution`, then `max_integrality_violation` is nonzero and `passed` is `False`. | REQ-009 |
| AC-009 | Given any of AC-001 through AC-004's solved results, when `result.shadow_prices`-equivalent (`reporting.shadow_prices.build_shadow_prices`) is inspected via the assembled `OptimizationResult`, then it is empty (no LP duals reported for a MIP solve). | NFR-003 |

## Data & Dependencies

- `domain.loans.LoanRoute.all_or_none`, `.lot_size_shares`, `.minimum_active_quantity_shares`
  (already implemented, T04) — read-only inputs to REQ-001/002/003.
- `domain.policies.UtilizationPolicy` — gains `maximum_active_routes` (REQ-004); every other field
  unchanged.
- `formulation.lp.compile_lp`'s `REQUIRED_CONSTRAINTS`/`REQUIRED_OBJECTIVES` and the baseline
  components themselves (T08) — reused unchanged by `compile_mip`.
- `solvers.highs.HighsBackend`, `ports.solver.SolverOptions`/`SolverResult` (T09) — already MIP-
  capable; no changes.
- `validation.solution_verifier.verify_solution` (T10) — already integrality-aware; no changes.
- `facade.InventoryOptimizer` (T12) — gains the auto-routing logic (REQ-007).
- `specs/engine_spec/TRACEABILITY.md`'s `LP-009` row — this spec's evidence target (MIP portion only;
  QP/PWL/NLP stay `SPECIFIED`).

## Risks

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| RISK-001 | Silently ignoring `all_or_none`/`lot_size_shares`/`minimum_active_quantity_shares` was the *pre-existing* behavior (nothing rejected it before this spec) — REQ-006's new rejection is itself a behavior change for `compile_lp`'s direct callers. | Any existing caller that happened to pass a route with one of these fields set (accepting the prior silent-ignore behavior) now gets a hard error instead of a wrong answer. | This is the intended, correct-by-construction outcome (P4) — a wrong silent answer is strictly worse than a clear rejection naming the fix (route to the facade, or to `compile_mip`). No current test in this repo exercises `compile_lp` directly with any of these fields set (confirmed by inspection), so nothing breaks in practice; documented here so it is not a surprise. |
| RISK-002 | Cardinality's binary-activation link (`q_j <= max_j * z_j`) adds a `z_j` for *every* route in a policy's scope, not just ones that individually request MIP treatment — a large desk-wide cardinality policy could add many more binary variables than the other three triggers combined, with real solve-time cost. | A cardinality policy applied broadly could make a previously-fast LP solve noticeably slower. | Out of scope for a correctness spec to fix (it is inherent to what cardinality means); `plan.md`'s Validation Strategy notes this as a follow-up for the Core-desk-scale benchmark (`specs/0005-test-hardening/`) to eventually cover at MIP scale, not solved here. |
| RISK-003 | Combining triggers on one route (e.g. `all_or_none` and `lot_size_shares` together) is mathematically well-defined only if `maximum_quantity_shares` happens to be a multiple of `lot_size_shares` — otherwise the model is trivially infeasible with no diagnostic beyond the standard `INFEASIBLE` status. | A desk user combining triggers without realizing the numeric incompatibility gets an opaque infeasibility, not a clear explanation. | Explicitly a Non-Goal for this pass (untested combination); `plan.md`'s Follow-ups tracks a friendlier diagnostic for later. |

## Assumptions & Open Questions

- Assumption: a route with `all_or_none=True` and a nonzero `hard_minimum_quantity_shares` is an
  edge case this spec does not special-case — the existing `hard_minimum` lower bound and the new
  `q_j = max_j * z_j` equality compose naturally (the LP becomes infeasible at `z_j=0` unless
  `hard_minimum=0`, correctly forcing `z_j=1` always in that case, not a bug requiring extra code).
- Assumption: cardinality's `z_j` binaries are shared with REQ-001/002's binaries when a route
  qualifies for both, not duplicated — one `z` variable per route, reused across every applicable
  constraint component.
- Open question: whether `facade.InventoryOptimizer` should expose *which* path it took
  (`compile_lp` vs `compile_mip`) anywhere in `OptimizationResult` for observability. `plan.md`
  resolves this by reusing `CompiledProblem.formulation` (already a field, already surfaced
  nowhere in T11's result — a pre-existing, separate small gap `plan.md` notes but does not fix
  here, to keep this spec's scope bounded to MIP triggers themselves).

## Exceptions

None recorded.
