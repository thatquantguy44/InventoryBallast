# Plan: Deterministic multi-period settlement (Phase 5 item 2, deterministic form)

- **Spec:** 0010-multi-period-settlement (`spec.md`)
- **Status:** Draft
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code)
- **Last updated:** 2026-09-07

> HOW. This plan requires an approved `spec.md`. Every requirement in the spec
> must appear in the traceability matrix below. **`spec.md` is not yet approved** —
> three open design questions need owner sign-off first (see its Open Questions). This plan
> describes how the recommended design (deterministic forward projection) would be built if
> approved as scoped.

## Approach

Treat this as a pure, additive **reporting** extension, not a new compiler. Period 0 stays exactly
today's existing single-period LP/MIP/QP solve, untouched. Periods 1..N are produced by walking the
already-solved period-0 book forward through `OptimizationRequest.planning_periods`, reapplying the
*existing, unchanged* per-trade-event-type mechanics `scenarios.apply.apply_scenario` already
implements for all seven `TradeEventType` kinds — the same balance-identity arithmetic (adjusting
`total_lendable_shares`/`on_loan_shares`/`available_to_lend_shares`/route `current_quantity_shares`)
that already correctly reproduces `EXAMPLES.md` E2/E3, just called once per period instead of once
for the whole scenario.

**The key refactor: extract `apply_scenario`'s cutoff-and-apply logic so it takes an explicit date
range instead of hardcoding `baseline.effective_date`.** Today `apply_scenario` does, inline:

```python
effective_events = sorted(
    (e for e in scenario.trade_events if e.effective_date <= baseline.effective_date),
    key=lambda e: (e.effective_date, _TYPE_PRIORITY[e.event_type], e.event_id),
)
# ... apply each event to inventory_by_id / routes_by_id ...
```

Split this into two reusable pieces in `scenarios/apply.py` (promoted from private to
package-shared, the same move `formulation.compiler_support` already made for
`resolve_component`/`set_route_bounds` when a second compiler needed them):

```python
def select_effective_events(
    events: Sequence[TradeEvent], *, after: date | None, on_or_before: date
) -> list[TradeEvent]:
    """Section 13.3 step 3's deterministic order, generalized to an arbitrary window instead of
    always ``(-inf, baseline.effective_date]``."""
    return sorted(
        (e for e in events if (after is None or e.effective_date > after)
         and e.effective_date <= on_or_before),
        key=lambda e: (e.effective_date, _TYPE_PRIORITY[e.event_type], e.event_id),
    )

def apply_events(
    baseline: OptimizationRequest, events: Sequence[TradeEvent]
) -> tuple[OptimizationRequest, tuple[str, ...]]:
    """The existing per-event-type mutation loop (`_apply_trade_event`), unchanged, now returning
    a new request instead of mutating local dicts that `apply_scenario` then reassembles inline."""
    ...
```

`apply_scenario` becomes a thin, behavior-identical wrapper: `select_effective_events(scenario.
trade_events, after=None, on_or_before=baseline.effective_date)` then `apply_events(...)`, plus its
existing rate/demand-shock handling and `request_id` renaming, unchanged. **Its own existing 16
tests must keep passing, unchanged, as the acceptance bar for this refactor** — this is what makes
the reuse genuinely safe rather than a parallel reimplementation (RISK-004).

The new `settlement/project.py::project_multi_period` then calls `apply_events` once per period,
chaining forward:

```python
def project_multi_period(
    request: OptimizationRequest, result: OptimizationResult, config: InventoryOptimizerConfig
) -> MultiPeriodProjection:
    settled = _settle_period_zero(request, result)          # REQ-004
    boundaries = (request.effective_date, *request.planning_periods)
    states = [settled]
    all_warnings: list[str] = []
    for previous_boundary, this_boundary in itertools.pairwise(boundaries):
        events = select_effective_events(
            request.known_future_events, after=previous_boundary, on_or_before=this_boundary
        )
        updated, warnings = apply_events(states[-1], events)
        states.append(updated)
        all_warnings.extend(warnings)
    return _build_projection(request, result, states, boundaries, config, all_warnings)  # REQ-005/006/009
```

`_settle_period_zero` builds period 0's state from `result.allocations`/`result.balances` directly
(the already-independently-verified post-solve numbers), not by re-deriving them — `result.
balances[i].post_on_loan_shares`/`post_available_shares` and each route's solved
`post_quantity_shares` become period 0's `current_quantity_shares`/inventory fields. This also means
`project_multi_period` never needs to know which compiler produced `result` (REQ-008).

## Architecture & Components

```
domain/requests.py        + planning_periods, known_future_events fields (REQ-001, REQ-002)
domain/settlement.py       (new) PeriodBalance, PeriodEconomics, MultiPeriodProjection (REQ-007)
config/models.py          + MultiPeriodConfig.daily_discount_rate (REQ-006)
scenarios/apply.py         select_effective_events / apply_events promoted from private helpers,
                           reused unchanged by apply_scenario (REQ-003)
settlement/__init__.py     (new package, mirrors scenarios/)
settlement/project.py      (new) project_multi_period (REQ-003 through REQ-009)
```

No file under `formulation/`, `components/`, `solvers/`, or `validation/` changes at all (REQ-008)
— the same "zero touch to the compiler" property `specs/0004-scenario-engine/` established for its
own scenario engine, here extended one step further: `settlement/` doesn't even touch
`formulation/context.py` the way `scenarios/` reads `BuildContext` for comparison reporting: it
consumes only the already-built `OptimizationResult`.

## Interfaces & Data Contracts

```python
# domain/requests.py additions
planning_periods: tuple[date, ...] = ()        # strictly increasing, all > effective_date
known_future_events: tuple[TradeEvent, ...] = ()  # empty unless planning_periods is non-empty

# domain/settlement.py (new)
class PeriodBalance(BaseModel):
    inventory_id: str
    period_index: int          # 0 = the solved baseline; 1..N = projected
    period_date: date          # effective_date for period 0; the boundary date otherwise
    total_lendable_shares: float
    on_loan_shares: float
    available_to_lend_shares: float
    utilization: float

class PeriodEconomics(BaseModel):
    period_index: int
    period_date: date
    day_count_fraction: float               # (this_boundary - previous_boundary).days / divisor
    undiscounted_net_revenue_usd: float     # sum of fee_revenue_coefficient * quantity, this period
    discount_factor: float                  # (1 + daily_discount_rate) ** -days_since_effective_date
    discounted_net_revenue_usd: float

class MultiPeriodProjection(BaseModel):
    request_id: str
    planning_periods: tuple[date, ...]
    balances: tuple[PeriodBalance, ...]      # len == periods x inventory records
    economics: tuple[PeriodEconomics, ...]   # len == periods
    total_discounted_net_revenue_usd: float
    warnings: tuple[str, ...]                # NFR-004: from apply_events, never swallowed
    disclosure: str                          # REQ-009; always the fixed sentence below, set only
                                              # by project_multi_period -- see NFR-003

# config/models.py addition
class MultiPeriodConfig(BaseModel):
    daily_discount_rate: float = Field(default=0.0, ge=0.0)  # 0.0 = no discounting (default)
# InventoryOptimizerConfig gains: multi_period: MultiPeriodConfig = Field(default_factory=...)
```

`disclosure` is always exactly: *"Period 0 is the solved allocation. Periods 1..N are a mechanical
projection of already-known future events against that allocation, not a re-optimized plan."*
`project_multi_period` is documented as the only sanctioned constructor of `MultiPeriodProjection`
(AC-007 pins the exact string; nothing structurally prevents a caller from hand-constructing a
different one, matching how this repo does not lock every invariant at the type level, but the
one public entry point never varies it).

## Constitution Check

| Principle | Upheld? | Notes |
| --- | --- | --- |
| P4 Correct by construction | yes | Reuses `apply_events`'s already-tested per-event-type mechanics unchanged rather than re-deriving balance arithmetic a second time; `NFR-004` refuses to silently clip an invariant violation. |
| P5 Reversibility | yes | Purely additive (two new optional request fields, one new package, one new config section); deleting `settlement/` and the two request fields fully reverts this spec. |
| P6 Observability | yes | `MultiPeriodProjection.warnings` surfaces every `apply_events` warning; `disclosure` makes the projection's own honest scope unmissable (REQ-009). |
| P9 Security & data | yes | No new external data source; every input is already-validated domain data the caller supplies. |

## Traceability Matrix

`specs/spec002/TRACEABILITY.md` carries no existing row for §22.11/§22.12 — this is a genuinely new
area. Proposes two new rows (task T-011 below), prefixed `MPS-` (Multi-Period Settlement) rather
than overloading `SCN-*` (which is specifically the single-period what-if scenario engine) or
`LP-*` (the baseline single-period LP):

| ID | Evidence | Task |
| --- | --- | --- |
| REQ-001 | `domain/requests.py::OptimizationRequest.planning_periods`/`.known_future_events` + validators | T-001 |
| REQ-002 | Same validator (empty-events-without-periods rejection) | T-001 |
| REQ-003 | `scenarios/apply.py::select_effective_events`/`apply_events` (promoted, reused); `settlement/project.py`'s per-period loop | T-002, T-003 |
| REQ-004 | `settlement/project.py::_settle_period_zero` | T-003 |
| REQ-005 | `settlement/project.py`'s `PeriodBalance` construction | T-003 |
| REQ-006 | `config/models.py::MultiPeriodConfig`; `settlement/project.py`'s `PeriodEconomics` construction, reusing `fee_revenue_coefficient` | T-004, T-005 |
| REQ-007 | `domain/settlement.py::MultiPeriodProjection`/`PeriodBalance`/`PeriodEconomics` | T-004 |
| REQ-008 | No changes to `formulation/`, `components/`, `solvers/`, `validation/` (verified by an architecture-boundary test mirroring `tests/unit/test_architecture_boundaries.py`) | T-006 |
| REQ-009 | `MultiPeriodProjection.disclosure`, always set by `project_multi_period` | T-003 |
| REQ-010 | `tests/golden/test_multi_period_settlement.py`, `tests/unit/test_settlement_project.py` | T-007 |
| NFR-001 | Full existing suite (239, pre-this-spec) unchanged; `facade.optimize()` untouched | T-007 |
| NFR-002 | No calendar dependency; documented simplification | spec.md Non-Goals |
| NFR-003 | `disclosure` field, unconditional | T-003 |
| NFR-004 | Reuses `ScenarioApplicationError`/warning behavior from `apply_events` | T-002, T-003 |

New `specs/spec002/TRACEABILITY.md` rows (T-011): `MPS-001` (deterministic multi-period balance
projection, §22.11's identities) and `MPS-002` (formulation-independence — no compiler/component
change).

## Trade-offs & Alternatives

**Design A — full joint multi-period LP** (§22.11's literal formula sketch): introduce
route-per-period decision variables (`q_j,t`), extend `formulation/context.py` with a time-indexed
`BuildContext`, and let the objective jointly optimize across the whole horizon so period-0
allocation can legitimately trade off against period 3's outcome. This is the *complete* answer to
§22.11, but multiplies variable/row count by the route count times the period count (the same
`J*K`-shaped growth `specs/0009-discrete-fee-tier-pricing/spec.md` RISK-001 flagged for its own
tier dimension, here larger since every route carries it, not just tiered-group routes), needs
time-varying route bounds/eligibility that do not exist today, and needs a real calendar. It also
changes what "the decision" means — period-0's allocation is no longer independently explainable
the way every other formulation in this repo has been (Section 18.3's reason codes all assume a
route's quantity is explained by *that period's own* coefficients and constraints).

**Design B — deterministic forward projection** (chosen, pending owner sign-off — spec.md's Open
Questions): period 0 stays the only decision, exactly as today; periods 1..N are a mechanical,
unoptimized projection of what already-known future events will do to the already-solved book.
Strictly smaller: no new decision variables, no compiler change, no calendar, and it reuses
`apply_events`'s already-tested mechanics rather than inventing new balance arithmetic. The
trade-off: it cannot answer "should I lend less today because of a recall I already know about
three days out" — it can only *tell you* what that recall will do, given today's allocation as
already decided. `specs/0009-discrete-fee-tier-pricing/` chose the analogous "smaller, honest,
discrete" answer over "complete, harder, continuous" for the same reason (§12.5's own sanctioned
alternative); this plan makes the same call here, but flags it explicitly rather than assuming the
owner would make the identical trade-off unprompted.

**Refactoring `apply_scenario` in place vs. duplicating its logic in `settlement/`:** duplicating
would be lower-risk to `scenarios/`'s own existing behavior in isolation, but would mean two
independently-maintained copies of Section 13's balance-identity arithmetic silently drifting apart
over time — exactly the kind of "one economic concept, two code paths" `specs/0009-discrete-fee-
tier-pricing/plan.md` already reasoned through and rejected for its own delta-revenue term. The
refactor's own existing-test acceptance bar (RISK-004) is the mitigation, not skipping the reuse.

**Discount rate default (zero) vs. requiring a configured rate:** zero matches every other
zero-default extension in this repo (`ObjectiveConfig.allocation_stability_penalty`) and keeps a
config predating this field behaving identically; requiring a rate would be more realistic but
would make this spec's very first fixture undefined without a business input this spec has no
authority to invent. Flagged as an open question rather than assumed.

## Validation Strategy

- `tests/unit/test_scenario_apply.py` (existing, T13-T14) — must keep passing unchanged after the
  `select_effective_events`/`apply_events` extraction, proving the refactor is behavior-preserving
  (RISK-004) before any new code is layered on top.
- `tests/golden/test_multi_period_settlement.py` — the worked fixture below (AC-003/AC-004/AC-005).
- `tests/unit/test_settlement_project.py` — boundary/ordering unit tests: an event exactly on a
  period boundary lands in that period, not the next; `known_future_events` beyond the last
  `planning_periods` date is retained but never applied (mirrors §13.2's own existing "later events
  ... do not affect" wording, extended one step); the REQ-002 validator; formulation-independence
  (AC-006) via a MIP-triggering and a QP-triggering fixture.
- `tests/unit/test_domain_contracts.py` additions — `planning_periods`/`known_future_events` field
  validation (AC-002, and `planning_periods` ordering).
- Full suite rerun (AC-001/NFR-001).

### Worked fixture sketch (for the golden tests)

One inventory (`INV-1`, 100 lendable shares, `price_usd=10.0`), one route (`RT-A`, solved to fill
its full 100 shares at period 0, `fee_rate=0.02`, `revenue_share=1.0`, `variable_cost_rate=0.0`),
`act_360`/`planning_horizon_days=1` (so a one-day period's `day_count_fraction = 1/360`),
`daily_discount_rate=0.0` (so `discount_factor = 1.0` throughout — proving the mechanism without a
second, independent discounting computation to also get right by hand). `planning_periods =
(effective_date + 1 day, effective_date + 3 days)`; `known_future_events` contains one `RECALL`
event (`route_id=RT-A`, `quantity_shares=40`, `effective_date = effective_date + 3 days`) — landing
in period 2, not period 1.

Expected: period 1's `on_loan_shares`/`available_to_lend_shares` for `INV-1` equal period 0's
exactly (no event fell in `(effective_date, effective_date+1]`); period 2's `on_loan_shares` drops
by 40 (`100 -> 60`) and `available_to_lend_shares` rises by 40 (`0 -> 40`), matching
`_adjust_on_loan`'s existing, unchanged arithmetic. Period 2's undiscounted revenue =
`10.0 * (1/360) * 0.02 * 60 = 0.0333...` (the post-recall quantity, not the pre-recall one) —
computed in the test from the formula, never pasted from a solve, matching the convention
`specs/0006`–`0009` all used for their own hand-computed fixtures.

## Rollout, Observability & Rollback

Purely additive: two new optional request fields, one new config section (zero-default), one new
package, one new result type. Rollback is deleting `settlement/`, `domain/settlement.py`, the two
request fields, and `MultiPeriodConfig`. Observability is `MultiPeriodProjection.warnings` plus its
unconditional `disclosure` field. No existing module's behavior changes for any request that leaves
`planning_periods` empty (NFR-001) — the same "inert unless opted into" guarantee every extension
since `specs/0006-mip-business-rules/` has upheld.

## Open Questions

Mirrors `spec.md`'s Open Questions (all three need owner sign-off before `spec.md`/this plan can
move to Approved):

- Deterministic projection (this plan) vs. the full joint multi-period LP (Design A) — see
  Trade-offs & Alternatives.
- Whether `LoanRoute.recall_notice_days` should be validated against a known future `RECALL`
  event's timing in V1, or deferred (this plan defers it).
- The default `daily_discount_rate` (this plan proposes zero).
