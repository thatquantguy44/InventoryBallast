# Plan: Scenario engine and basic stress testing (T13-T14)

- **Spec:** 0004-scenario-engine (`spec.md`)
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code, implemented as described below)
- **Last updated:** 2026-09-05

> HOW. This plan requires an approved `spec.md`. Every requirement in the spec
> must appear in the traceability matrix below.

## Approach

Two new packages, mirroring `reporting/`'s own split between plain-data types and behavior:

1. **`domain/scenarios.py`** — `TradeEventType` (added to `domain/enums.py`, alongside the other
   enums), `TradeEvent`, `RateShock`, `DemandShock`, `Scenario`. Frozen, `extra="forbid"` pydantic
   models, matching every other `domain/*.py` contract.
2. **`domain/scenario_results.py`** — `RouteAllocationDelta`, `InventoryBalanceDelta`,
   `ScenarioComparison`, `StressScenarioOutcome`, `StressTestReport`. Same "domain imports nothing
   from formulation/validation/reporting" discipline `domain/results.py` (T11) established;
   `reporting.types`/`facade` types are converted at assembly time, not embedded by reference.
3. **`scenarios/` package** (top-level, sibling to `reporting/`):
   - `apply.py` — `apply_scenario(baseline, scenario) -> (OptimizationRequest, warnings)`.
   - `compare.py` — `build_scenario_comparison(baseline_result, scenario_result, scenario,
     baseline_request, scenario_request) -> ScenarioComparison`.
   - `runner.py` — `run_scenario`, `run_scenarios`, `run_stress_test`.
4. **`services.py`** gains `ScenarioService` (a `runtime_checkable` Protocol, finally defined) and
   `ScenarioServiceImpl`.
5. **`cli.py`**'s `_cmd_scenarios` becomes a real handler.

Nothing in `facade.py`, `formulation/`, `solvers/`, `validation/`, or `reporting/` changes its
existing contract — every scenario re-solve is a plain call to the already-existing
`InventoryOptimizer.optimize()`.

### Reconciling a sale against an existing book (the load-bearing design decision)

E3's own setup ("treat the E1 result as the current book") requires a baseline where
`SecurityInventory.on_loan_shares == 100` (the sum of both routes' `current_quantity_shares`,
already required by `validation.reconciliation.check_on_loan_reconciliation`) and
`available_to_lend_shares == 0`. A 30-share `SELL` then drops `total_lendable_shares` to 70 — below
`on_loan_shares`. Recomputing `available_to_lend_shares` from the balance identity
(`total_lendable - on_loan - reserved - committed`) would produce **-30**, which
`SecurityInventory`'s own field constraint (`Field(ge=0.0)`) rejects at *construction* time.

Three ways to resolve this were considered:

- **(A) Relax `SecurityInventory`'s field constraints** (allow `available_to_lend_shares < 0`, drop
  the "`on_loan_shares` cannot exceed `total_lendable_shares`" check) so a fully-reconstructed,
  freshly-*validated* scenario inventory is representable. Rejected: this is a T03/T04 domain-model
  change to an already-tested contract, for a state (`SecurityInventory` under water) that a
  desk's real-time book can transiently be in (a sale settles before its offsetting recall
  completes) but that this repo's steady-state ingestion path has good reason to keep rejecting as
  a likely data error. Changing it for everyone to support one scenario case is the wrong trade.
- **(B) Model the sale as a change to a not-yet-built field** (e.g., a new "pending recall" bucket)
  distinct from `total_lendable_shares`. Rejected: invents new domain-contract surface with no
  worked example or spec text backing its shape — the same overreach `LP-008`/`InventoryShock` were
  rejected for elsewhere in this repo's history.
- **(C) Never re-validate a scenario-modified `SecurityInventory` through `model_validate`/
  `model_dump_json`-then-reload; only ever `.model_copy(update=...)`, which does not re-run
  `@model_validator` checks.** **Chosen.** This is not a loophole being exploited by accident — it
  is the same mechanism `tests/unit/test_cli.py::test_validate_reports_every_issue_not_just_first`
  (T12) already relies on, deliberately, to distinguish "constructed in-memory" from "round-tripped
  through JSON" pydantic instances. `apply_scenario` only ever produces its result via
  `.model_copy()`; it is handed directly, in-process, to `InventoryOptimizer.optimize()` — never
  serialized to JSON and reloaded mid-pipeline. The *LP itself* never reads `on_loan_shares`/
  `available_to_lend_shares` at all (`InventoryBalanceConstraint`'s row uses only
  `total_lendable_shares`/`reserved_shares`/`committed_out_shares`, and
  `TransitionIdentityConstraint` uses `route.current_quantity_shares` as the pre-trade baseline) —
  so the LP correctly produces E3's exact `q_A=70, q_B=0` result regardless of what
  `available_to_lend_shares` says. `validation.raise_if_invalid` (re-run per REQ-006) also never
  re-checks a record's own field-level identity — it only checks freshness and cross-record
  reconciliation (`check_on_loan_reconciliation` etc.), and a plain `SELL` does not touch any route,
  so that check still holds untouched.

  The one place this *is* surfaced honestly: `available_to_lend_shares` is still recomputed (from
  the same balance identity, using the new `total_lendable_shares`) purely for reporting
  consistency in `BalanceRecord`'s output — and REQ-007 requires an explicit warning whenever that
  recomputation goes negative, so the state is visible, not silently hidden behind a value that
  happens not to crash. `on_loan_shares` itself is left untouched by inventory-level events (`BUY`/
  `SELL`/`TRANSFER_*`) — it is a snapshot of shares out on loan as of the original `as_of`, a
  historical fact a hypothetical future trade does not retroactively rewrite. Route-level events
  (`RETURN`/`RECALL`) are different: they change a specific route's `current_quantity_shares`
  directly, so *those* two event types also adjust the owning inventory's `on_loan_shares` (and,
  from the identity, `available_to_lend_shares`) by the same amount — otherwise
  `check_on_loan_reconciliation` (which *is* re-run) would immediately fail.

  **Constraint this decision imposes:** a scenario-modified `OptimizationRequest` must never be
  serialized to JSON and reloaded before solving. `cli.py`'s `scenarios` handler loads the
  *baseline* request and the `Scenario` from JSON, then keeps everything in-process from
  `apply_scenario` through `InventoryOptimizer.optimize()` — it does not write an intermediate
  "scenario request" file the way `optimize`'s `--output` does for a final result.

## Architecture & Components

```
domain/enums.py
  + TradeEventType(StrEnum): BUY, SELL, TRANSFER_IN, TRANSFER_OUT, NEW_LOAN, RETURN, RECALL

domain/scenarios.py
  TradeEvent, RateShock, DemandShock, Scenario

domain/scenario_results.py
  RouteAllocationDelta, InventoryBalanceDelta, ScenarioComparison,
  StressScenarioOutcome, StressTestReport

scenarios/
  apply.py     # apply_scenario(baseline, scenario) -> (OptimizationRequest, warnings)
  compare.py   # build_scenario_comparison(...) -> ScenarioComparison
  runner.py    # run_scenario, run_scenarios, run_stress_test

services.py
  + ScenarioService(Protocol): run(baseline, scenarios) -> tuple[ScenarioComparison, ...]
  + ScenarioServiceImpl

cli.py
  _cmd_scenarios  # now real: --request, --scenario, --config, --output
```

`exceptions.py` gains `ScenarioApplicationError` (REQ-003/REQ-004's structured-rejection type),
matching `AttributionMismatchError`'s own "never silently continue" pattern from T11.

## Interfaces & Data Contracts

```python
# domain/scenarios.py
class TradeEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_id: str
    event_type: TradeEventType
    trade_date: date
    effective_date: date
    settlement_date: date
    quantity_shares: float = Field(gt=0.0, allow_inf_nan=False)
    inventory_id: str | None = None   # BUY, SELL, TRANSFER_IN, TRANSFER_OUT
    route_id: str | None = None        # NEW_LOAN, RETURN, RECALL
    trade_price_usd: float | None = Field(default=None, gt=0.0)  # BUY/SELL context only, never
                                                                   # part of the lending objective
    source: str
    source_version: str
    # model_validator: inventory_id required for the four supply-side types, route_id required
    # for the three route-side types (mutually exclusive by event_type).

class RateShock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    shock_id: str
    route_id: str
    new_fee_rate: float = Field(allow_inf_nan=False)
    source: str
    source_version: str

class DemandShock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    shock_id: str
    demand_group_id: str
    reference_quantity_shares: float | None = Field(default=None, ge=0.0)
    reference_fee_rate: float | None = Field(default=None, ge=0.0)
    elasticity: float | None = Field(default=None, ge=0.0)
    hard_max_quantity_shares: float | None = Field(default=None, ge=0.0)
    source: str
    source_version: str
    # model_validator: at least one override field set.

class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    scenario_id: str
    name: str
    trade_events: tuple[TradeEvent, ...] = ()
    rate_shocks: tuple[RateShock, ...] = ()
    demand_shocks: tuple[DemandShock, ...] = ()
    metadata: Mapping[str, str] = Field(default_factory=lambda: MappingProxyType({}))
    # field_serializer on metadata (same MappingProxyType fix as T12's domain/requests.py).
    # model_validator: trade_events event_id values unique.
```

```python
# scenarios/apply.py
_TYPE_PRIORITY: dict[TradeEventType, int] = {
    TradeEventType.BUY: 0, TradeEventType.SELL: 1, TradeEventType.TRANSFER_IN: 2,
    TradeEventType.TRANSFER_OUT: 3, TradeEventType.NEW_LOAN: 4, TradeEventType.RETURN: 5,
    TradeEventType.RECALL: 6,
}  # §13.1's own listed order; no ordering is given anywhere else (spec.md's Assumptions)

def apply_scenario(baseline: OptimizationRequest, scenario: Scenario) -> OptimizationRequest:
    _check_no_conflicting_return_recall(scenario)  # REQ-003

    effective = sorted(
        (e for e in scenario.trade_events if e.effective_date <= baseline.effective_date),
        key=lambda e: (e.effective_date, _TYPE_PRIORITY[e.event_type], e.event_id),
    )
    inventory_by_id = {i.inventory_id: i for i in baseline.inventory}
    routes_by_id = {r.route_id: r for r in baseline.routes}
    warnings: list[str] = []

    for event in effective:
        _apply_trade_event(event, inventory_by_id, routes_by_id, warnings)  # REQ-004, RISK-001
    for shock in scenario.rate_shocks:
        routes_by_id[shock.route_id] = routes_by_id[shock.route_id].model_copy(
            update={"fee_rate": shock.new_fee_rate}
        )
    for shock in scenario.demand_shocks:
        # apply only the fields the shock actually overrides, onto the named DemandForecast

    return baseline.model_copy(update={
        "request_id": f"{baseline.request_id}::{scenario.scenario_id}",
        "inventory": tuple(inventory_by_id[i.inventory_id] for i in baseline.inventory),
        "routes": tuple(routes_by_id[r.route_id] for r in baseline.routes),
        "demand": tuple(...),  # demand-shocked forecasts substituted in place
    })
```

`_apply_trade_event`'s per-type effect (all via `.model_copy()`, never in-place):

| Event type | Inventory effect | Route effect |
| --- | --- | --- |
| `BUY` | `total_lendable_shares += qty`; `available_to_lend_shares` recomputed from the identity | none |
| `SELL` | `total_lendable_shares -= qty` (rejected if this would go negative, REQ-004); `available_to_lend_shares` recomputed (may go negative — warning appended, RISK-001) | none |
| `TRANSFER_IN` | same as `BUY`, only if `inventory.eligible` | none |
| `TRANSFER_OUT` | same as `SELL` | none |
| `NEW_LOAN` | none | `eligible=True` (optionally raises `maximum_quantity_shares` if the event's `quantity_shares` is read as an override — see spec.md's Assumptions) |
| `RETURN` | `on_loan_shares -= returned`, `available_to_lend_shares += returned` | `current_quantity_shares -= returned` where `returned = min(qty, current)` |
| `RECALL` | same on_loan/available adjustment, only for the *forced* portion | `maximum_quantity_shares` lowered (floored at `hard_minimum_quantity_shares`); `current_quantity_shares` reduced to the new maximum if it now exceeds it |

```python
# scenarios/runner.py
def run_scenario(
    baseline_request: OptimizationRequest,
    baseline_result: OptimizationResult,
    scenario: Scenario,
    optimizer: InventoryOptimizer,
) -> ScenarioComparison:
    scenario_request = apply_scenario(baseline_request, scenario)
    raise_if_invalid(scenario_request)  # REQ-006; re-raises as InputValidationError if broken
    scenario_result = optimizer.optimize(scenario_request)
    return build_scenario_comparison(
        scenario=scenario,
        baseline_request=baseline_request, baseline_result=baseline_result,
        scenario_request=scenario_request, scenario_result=scenario_result,
    )

def run_scenarios(
    baseline_request, baseline_result, scenarios: Sequence[Scenario], optimizer
) -> tuple[ScenarioComparison, ...]:
    return tuple(
        run_scenario(baseline_request, baseline_result, scenario, optimizer)
        for scenario in scenarios
    )  # REQ-008: literally the same function, called in a loop -- batch == isolated by construction

def run_stress_test(
    baseline_request, baseline_result, scenarios, optimizer
) -> StressTestReport:
    comparisons = run_scenarios(baseline_request, baseline_result, scenarios, optimizer)
    ...  # aggregate: feasible/infeasible counts, worst-case by objective delta among feasible ones
```

`build_scenario_comparison` (in `scenarios/compare.py`) reads two already-built `OptimizationResult`
objects plus the two requests (baseline and scenario-modified) — never a `VerifiedSolution`,
matching T11's `ExplanationServiceImpl` precedent of reading only already-built results. Per-route
`TRADE_REDUCED_SUPPLY` tagging: a route whose `post_quantity_shares` decreased between baseline and
scenario **and** whose `inventory_id` was touched by an effective, supply-reducing trade event
(`SELL`, `TRANSFER_OUT`, or a forced portion of `RETURN`/`RECALL`) in this scenario. Its estimated
lost revenue: `(scenario_q - baseline_q) * fee_revenue_coefficient(route, inventory,
config.formulation)` — reusing the exact function `reporting.explanations` already imports, so
there is only ever one definition of that coefficient in the codebase.

## Constitution Check

| Principle | Upheld? | Notes |
| --- | --- | --- |
| P4 Correct by construction | yes | `apply_scenario` never silently drops a conflicting event (REQ-003) or an impossible sale (REQ-004); an oversold-pending-recall state is surfaced as a warning, never hidden (REQ-007). No new look-ahead: events are gated strictly by `effective_date <= request.effective_date`. |
| P5 Reversibility | yes | `scenarios/`, `domain/scenarios.py`, `domain/scenario_results.py` are wholly additive new modules; `services.py`/`cli.py` diffs are additive (`ScenarioService` was previously undefined, `_cmd_scenarios` previously always failed). Nothing in `facade.py`/`formulation/`/`validation/`/`reporting/` changes. |
| P6 Observability | yes | `ScenarioComparison.warnings` surfaces the oversold-pending-recall case explicitly; every rejection (REQ-003/004/006) raises a structured, named exception rather than continuing silently. |
| P9 Security & data | yes | No secrets, credentials, or client-identifying data; scenario files are caller-named local files, same as `optimize`'s `--request`/`--config`. |

## Traceability Matrix

| Requirement | Design element | Tasks |
| --- | --- | --- |
| REQ-001 | `domain/scenarios.py`; `domain/enums.py::TradeEventType` | T-001 |
| REQ-002 | `scenarios/apply.py::apply_scenario` | T-002 |
| REQ-003 | `scenarios/apply.py::_check_no_conflicting_return_recall`; `exceptions.ScenarioApplicationError` | T-002 |
| REQ-004 | `scenarios/apply.py::_apply_trade_event` (`SELL`/`TRANSFER_OUT` branch) | T-002 |
| REQ-005 | `scenarios/apply.py::apply_scenario` (rate/demand shock loops) | T-002 |
| REQ-006 | `scenarios/runner.py::run_scenario` (`raise_if_invalid` call) | T-003 |
| REQ-007 | `domain/scenario_results.py::ScenarioComparison`; `scenarios/compare.py::build_scenario_comparison` | T-004 |
| REQ-008 | `scenarios/runner.py::run_scenarios` | T-003 |
| REQ-009 | `services.py::ScenarioService`, `ScenarioServiceImpl` | T-005 |
| REQ-010 | `cli.py::_cmd_scenarios` | T-006 |
| REQ-011 | `scenarios/runner.py::run_stress_test`; `domain/scenario_results.py::StressTestReport` | T-007 |
| NFR-001 | `apply_scenario` uses only `.model_copy()`, never mutates | T-002, T-008 |
| NFR-002 | `run_scenarios` == loop over `run_scenario` | T-003, T-008 |
| NFR-003 | No `model_validate`/JSON round-trip of a scenario-modified request anywhere in `scenarios/`/`cli.py` | T-002, T-003, T-006 |

## Trade-offs & Alternatives

| Decision | Chosen | Rejected alternative | Why |
| --- | --- | --- | --- |
| Oversold-pending-recall representation | Never re-validate a scenario-modified request through `model_validate`; recompute `available_to_lend_shares` for reporting, warn if negative | Relax `SecurityInventory`'s field constraints | See "Reconciling a sale against an existing book" above — a T03/T04 domain-model change for one scenario case is the wrong trade. |
| `NEW_LOAN` semantics | Marks an existing candidate route `eligible=True` | Fabricate a brand-new `LoanRoute` inline from the event's own fields | `01_SPEC.md` says the event "requires a candidate route" (a reference), and `OptimizationRequest.routes` is fixed at construction; inventing new routes at scenario-apply time is a bigger, unrequested capability. |
| Per-route revenue estimate scope | Fee-revenue only, via the existing `fee_revenue_coefficient` | Build a new per-route-per-component attribution system | `EconomicsSummary` (T11) is deliberately per-component; a full per-route P&L system is a larger, separate piece of work with no worked example driving its shape yet. |
| Stress-test ranking | Objective delta alone | A weighted multi-metric score (objective + unfilled demand + utilization) | Simplest defensible default for a "basic" capability (this spec's explicit added scope); revisit once a real workflow has an opinion (spec.md's Open Questions). |

## Validation Strategy

- `tests/unit/test_scenarios_apply.py` — `apply_scenario` unit tests: immutability (NFR-001),
  timing gating, sort order, each `TradeEvent` type's effect, the two rejection paths (REQ-003/004),
  rate/demand shock application.
- `tests/golden/test_e2_rate_shock_scenario.py` — AC-001/002, reusing E2's exact numbers.
- `tests/golden/test_e3_sale_and_recall_scenario.py` — AC-003/004, both E3 variants.
- `tests/unit/test_scenarios_runner.py` — `run_scenario`/`run_scenarios` equivalence (AC-007),
  `run_stress_test` (AC-010).
- `tests/unit/test_services.py` (extended) — `ScenarioService` structural check (AC-008).
- `tests/unit/test_cli.py` (extended) — the `scenarios` subcommand, single and batch (AC-009).
- No backtest/leakage gates apply; the relevant quant gate is `repro` (NFR-001/002/003) via
  `hooks/stages/run-stage.sh`.

## Rollout, Observability & Rollback

Additive library + CLI surface; nothing else depends on `scenarios/` yet. No feature flag, no
staged rollout. Rollback is a plain revert of `scenarios/`, `domain/scenarios.py`,
`domain/scenario_results.py`, and the `services.py`/`cli.py`/`domain/enums.py`/`exceptions.py`
diffs — all additive, no existing behavior changes. Observability is `ScenarioComparison.warnings`
plus the test suite; `specs/spec002/TRACEABILITY.md`'s `SCN-001`-`SCN-003` rows and
`docs/handoff.md` are updated once implemented (tracked as T-009/T-010).

## Open Questions

- Whether `run_stress_test`'s report should be renderable through the CLI as its own subcommand
  (`inventory-optimizer stress`) or only as a library function callers compose themselves. This
  plan adds it as a library function only (`REQ-011` says nothing about a CLI surface); a CLI
  wrapper is a small follow-up once a real workflow asks for one.

## Deviations Discovered During Implementation

- **`apply_scenario` returns `(OptimizationRequest, tuple[str, ...])`, not a bare
  `OptimizationRequest`.** The oversold-pending-recall warning (RISK-001/REQ-007) has to originate
  somewhere, and computing it inside `_apply_trade_event` (where the relevant before/after values
  already exist) is simpler and less error-prone than re-deriving it later in
  `scenarios/compare.py` from the two requests alone. `run_scenario` threads these warnings into
  `ScenarioComparison.warnings` alongside `scenario_result.warnings`.
- **`InventoryOptimizer` gained a public `config` property.** `build_scenario_comparison` needs
  `InventoryOptimizerConfig.formulation` to call `fee_revenue_coefficient` for the
  `TRADE_REDUCED_SUPPLY` revenue estimate, and `run_scenario` needs
  `config.validation.max_staleness_hours` for the re-validation step (REQ-006). Threading `config`
  as a separate parameter through every function in `scenarios/` would duplicate what
  `InventoryOptimizer` already holds; exposing it as a read-only property is a small, backward-
  compatible addition to a T12 class this spec was otherwise told only to consume.
- **E2/E3 reproduced exactly, with no changes needed to `reporting/`, `formulation/`, or
  `validation/`.** This confirmed the plan's central design bet (never re-validate a
  scenario-modified request through `model_validate`) without requiring the fallback options (A)
  or (B) considered above.
