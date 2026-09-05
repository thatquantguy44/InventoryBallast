# Plan: Result, objective attribution, and explainability (T11)

- **Spec:** 0002-result-attribution-explainability (`spec.md`)
- **Status:** Draft
- **Author:** Joshua Lutkemuller (with `problem_formulation` / `solver_diagnostics_sensitivity` agent review)
- **Last updated:** 2026-09-04

> HOW. This plan requires an approved `spec.md`. Every requirement in the spec
> must appear in the traceability matrix below.

## Approach

Add a new `reporting/` package alongside the existing `formulation/`,
`solvers/`, and `validation/` packages, and extend `domain/results.py`'s
`OptimizationResult` in place (it is already the declared home for the
remaining thirteen §18.1 sections per its own module docstring). Nothing in
`formulation/`, `solvers/`, or `validation/solution_verifier.py` changes —
this work is purely a consumer of their already-implemented, already-tested
outputs (`CompiledProblem`, `SolverResult`, `VerificationReport`).

Three new concerns, three new modules, one orchestrator:

1. **Objective attribution** (`reporting/attribution.py`) — closes REQ-001/002.
2. **Decision explanations** (`reporting/explanations.py`) — closes REQ-004.
3. **Shadow prices** (`reporting/shadow_prices.py`) — closes REQ-005/006.
4. **Result assembly** (`reporting/result_builder.py`) — closes REQ-003,
   composing the three above plus balances/allocations/demand read directly
   off the domain request and the primal vector.

`components/interfaces.py`'s `ObjectiveComponent.attribute(self, solution:
object) -> object` gets its two `object` placeholders replaced by the new
`VerifiedSolution` / `ObjectiveAttribution` types (its own docstring already
names these as T11's job). `fee_revenue.py` and `transition_cost.py` each
implement `attribute()` for real instead of raising.

## Architecture & Components

```
domain/results.py
  OptimizationResult            # extended: 13 more §18.1 sections, still frozen/extra=forbid
  + AllocationRecord, BalanceRecord, EconomicsSummary, DemandSummary,
    ScheduleSummary, CollateralSummary, DeskSummary, SourceSummary,
    ConstraintReport, SolverDiagnostics, WarningsSummary, PlatformReference
    (VerificationReport from T10 is embedded as-is, not duplicated)

reporting/
  types.py           # VerifiedSolution, ObjectiveAttribution, RouteExplanation,
                      # ShadowPriceEntry -- the shared contracts every module below uses
  attribution.py     # attribute_objective(problem, result, verification) -> tuple[ObjectiveAttribution, ...]
  explanations.py    # explain_routes(problem, result, verification, request) -> tuple[RouteExplanation, ...]
  shadow_prices.py   # build_shadow_prices(problem, result, verification) -> tuple[ShadowPriceEntry, ...]
  result_builder.py  # build_optimization_result(request, problem, result, verification) -> OptimizationResult
```

`VerifiedSolution` is the single bundle every downstream module reads from —
`CompiledProblem`, `SolverResult`, `VerificationReport`, plus a
`primal_by_key(VariableKey) -> float` lookup built once over
`CompiledProblem.variable_index` so no module re-derives that mapping. This
also becomes the object `ObjectiveComponent.attribute()` receives, replacing
`solution: object`.

`components/registry.py` and `components/decorators.py` are unchanged;
`attribute_objective()` enumerates `CompiledProblem.manifest` (already a
`ComponentManifest` of `ComponentRegistration` for every component that ran),
filters to `kind == ComponentKind.OBJECTIVE`, instantiates/looks up each
component, and calls `.attribute(verified_solution)`.

## Interfaces & Data Contracts

```python
# reporting/types.py
@dataclass(frozen=True, slots=True)
class VerifiedSolution:
    problem: CompiledProblem
    result: SolverResult
    verification: VerificationReport

    def primal_at(self, key: VariableKey) -> float: ...   # 0.0 if key unknown or no primal

@dataclass(frozen=True, slots=True)
class ObjectiveAttribution:
    component_name: str          # matches ComponentRegistration.name, e.g. "fee_revenue"
    component_version: str
    unscaled_value_usd: float
    baseline_value_usd: float    # value at the unchanged/current-state allocation
    delta_usd: float             # unscaled_value_usd - baseline_value_usd

@dataclass(frozen=True, slots=True)
class RouteExplanation:
    route_id: str
    reason_codes: tuple[ReasonCode, ...]
    evidence: Mapping[str, float | str]   # e.g. {"net_fee_coefficient": 0.0123, "binding_row": "demand_cap:XYZ"}

@dataclass(frozen=True, slots=True)
class ShadowPriceEntry:
    row_key: RowKey
    dual_value: float
    objective_scale_usd: float    # copied from CompiledProblem.scaling for label correctness
    sign_convention: str           # fixed string, e.g. "maximize; positive = tightening relaxes objective by this much per unit"
```

`attribute_objective` raises `AttributionMismatchError(delta, tolerance)` (new,
in `inventory_optimizer.exceptions`) when
`abs(sum(a.unscaled_value_usd for a in attributions) -
result.objective_value_unscaled) > tolerance` — this is the fail-closed check
AC-003 requires; it is never caught and downgraded to a warning, matching
`solution_verifier.py`'s own no-silent-repair posture (constitution P4).

`explain_routes` reads, per route: the route's objective coefficients
(re-derived the same way `fee_revenue`/`transition_cost`'s `contribute()`
computed them, not re-read off `CompiledProblem.linear_objective` positionally
— avoids coupling to column order), the row(s) it participates in and their
slack (`row_upper/lower - constraint_matrix @ primal`, already computed once
in `solution_verifier.py`'s style), and the pre/post allocation delta. A
change is "material" when `abs(delta) > DEFAULT_TOLERANCE` (resolves the
spec's open question: reuse the verifier's tolerance, do not invent a second
one). Only routes clearing that bar get an entry; §18.3's 24 `ReasonCode`
values are matched by named, independent predicate functions (one per code)
so each is unit-testable in isolation — no single monolithic if/elif chain
that hides which evidence triggered which code.

`build_shadow_prices` returns an empty tuple whenever
`verified.result.dual is None or not verified.verification.passed` — covering
REQ-006 (MIP) and the "verification passed" precondition from §18.4 in one
guard. Otherwise it zips `CompiledProblem.row_index.keys` against
`result.dual` positionally (the same reversible mapping
`solution_verifier.py` already trusts) and labels every entry with the scale
from `CompiledProblem.scaling.objective_scale_usd`.

`OptimizationResult`'s new sections resolve the spec's other open question as
follows: sections with an implemented upstream source (Allocations, Balances,
Economics from attribution, Demand, Constraints from shadow prices,
Verification from T10, Solver from `SolverResult`) are always populated;
sections with no upstream source yet in this repo (Collateral, Schedules,
Sources, Desk) are typed as `X | None = None` rather than fabricated empty
models — `None` is an honest "not yet produced," matching §18.1's own
per-row optionality and constitution P6 (honest reporting over invented
completeness).

## Constitution Check

| Principle | Upheld? | Notes |
| --- | --- | --- |
| P4 Correct by construction | yes | Attribution hard-fails (`AttributionMismatchError`) rather than rounding away a mismatch; shadow prices hard-omit rather than guess for MIP. No look-ahead risk (this is a post-solve reporting layer, not a data pipeline). |
| P5 Reversibility | yes | `reporting/` is additive; nothing in `formulation/`/`solvers/`/`validation/` is modified. Reverting this spec's commits removes the package cleanly. |
| P6 Observability | yes | Every §18.1 section is either populated or explicitly `None` with a documented reason — no silent gaps, no hidden state read outside the three input objects. |
| P9 Security & data | yes | No secrets, credentials, or client-identifying data enter `reporting/`; inputs are already-computed numeric/domain objects from this repo's own prior stages. |

## Traceability Matrix

| Requirement | Design element | Tasks |
| --- | --- | --- |
| REQ-001 | `reporting/types.py::VerifiedSolution`/`ObjectiveAttribution`; `fee_revenue.py`/`transition_cost.py::attribute()` | T-001, T-002, T-003 |
| REQ-002 | `reporting/attribution.py::attribute_objective`; `AttributionMismatchError` | T-004 |
| REQ-003 | `domain/results.py` section models; `reporting/result_builder.py::build_optimization_result` | T-005, T-008 |
| REQ-004 | `reporting/explanations.py::explain_routes` | T-006 |
| REQ-005 | `reporting/shadow_prices.py::build_shadow_prices` | T-007 |
| REQ-006 | `reporting/shadow_prices.py` guard clause | T-007 |
| NFR-001 | Shared `DEFAULT_TOLERANCE` import from `validation/solution_verifier.py`, no re-declared constant | T-004 |
| NFR-002 | `OptimizationResult` never stores `CompiledProblem`/raw arrays, only derived scalars/records | T-005, T-008 |
| NFR-003 | `explain_routes`/`build_shadow_prices` use vectorized numpy ops over `constraint_matrix`/`primal`, no per-route Python loop touching a dataframe | T-006, T-007 |
| NFR-004 | All new functions are pure (no I/O, no `datetime.now()`, no random); enforced by unit tests calling twice and asserting equality | T-009 |

## Trade-offs & Alternatives

| Decision | Chosen | Rejected alternative | Why |
| --- | --- | --- | --- |
| Reason-code derivation | Independent predicate function per `ReasonCode`, evaluated against shared evidence | One monolithic scoring function producing all 24 at once | Independent predicates are unit-testable one code at a time (AC-005/006/007 each target a single code) and match how `01_SPEC.md` §18.3 lists them as independent, deterministic checks, not a ranked classifier. |
| Objective reconciliation tolerance | Reuse `solution_verifier.DEFAULT_TOLERANCE` | A separate, looser attribution-specific tolerance | A second tolerance is a second place to accidentally paper over the same class of bug VER-002 exists to catch; one tolerance keeps VER-001/002/006 mutually consistent by construction. |
| Missing §18.1 sections (Collateral/Schedules/Sources/Desk) | Typed `None` | Empty-but-present placeholder models with zeroed fields | A present-but-fake record is harder to distinguish from "genuinely zero" than an explicit `None`; matches constitution P6 (honest reporting) and avoids a second migration when those sections get real data sources later. |
| Shadow-price scope | LP-only (`dual is not None` guard), no MIP re-solve path | Build the optional §18.4 fixed-integer re-solve now | No MIP business rules exist yet (Phase 3 not started); building a re-solve path with nothing to test it against risks an untested, unreviewed code path. Tracked as a follow-up. |

## Validation Strategy

- Reuse the existing `tests/golden/` small/golden LP fixture(s) already
  exercised by T01-T10 rather than authoring a new fixture family — keeps
  attribution/explanation/shadow-price tests reconciling against the same
  known-good solve the verifier already trusts.
- One unit-test module per new `reporting/` file
  (`tests/unit/reporting/test_attribution.py`,
  `test_explanations.py`, `test_shadow_prices.py`, `test_result_builder.py`),
  plus a seeded-mismatch fixture (a hand-built `CompiledProblem`/`SolverResult`
  pair with a deliberately wrong `objective_value_unscaled`) for AC-003.
- Each `ReasonCode` predicate gets at least one positive fixture (code fires)
  and, for the two named in the spec (`HIGHER_NET_FEE`,
  `DEMAND_CAP_BINDING`), one negative fixture proving it does *not* fire on an
  immaterial change (AC-007).
- No backtest/leakage gates apply (this is a post-solve reporting layer, not a
  time-series pipeline); the relevant quant gate is `repro` (NFR-004,
  determinism) via `hooks/stages/run-stage.sh`.

## Rollout, Observability & Rollback

Pure library addition with no runtime consumer yet (T12's CLI/facade is the
first caller, and is out of scope here) — no feature flag, no staged rollout,
no production traffic at risk. Rollback is a plain revert of the `reporting/`
package and the `domain/results.py`/`components/interfaces.py` diffs; no data
migration, no persisted state. Observability is the tests themselves plus the
`TRACEABILITY.md` rows moving to `IMPLEMENTED` with a pointer to the specific
test names proving each row (per AC-010).

## Open Questions

- Whether `ObjectiveAttribution.baseline_value_usd` (the "unchanged baseline"
  §18.2 requires alongside the post-state total) reads from the route's
  `current`/pre-trade allocation already present on the domain request, or
  needs a second, explicit "baseline solve." Resolved here: read from the
  request's existing pre-trade allocation field — no second solve — since
  §18.2 only asks for "delta versus unchanged baseline," not a counterfactual
  optimization.
