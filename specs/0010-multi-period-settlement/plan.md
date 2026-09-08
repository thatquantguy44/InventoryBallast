# Plan: Multi-period settlement — deterministic projection and joint LP (Phase 5 item 2)

- **Spec:** 0010-multi-period-settlement (`spec.md`)
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code)
- **Last updated:** 2026-09-07

> HOW. This plan requires an approved `spec.md`. Every requirement in the spec
> must appear in the traceability matrix below.

## Approach

Deliver in two sequenced phases sharing one set of primitives, not two independent efforts:

**Phase 1 — shared fields, recall-notice validation, and the deterministic projection (Design
B).** Period 0 stays exactly today's existing single-period LP/MIP/QP solve. Periods 1..N are
produced by walking the already-solved period-0 book forward through
`OptimizationRequest.planning_periods`, reapplying the *existing, unchanged* per-trade-event-type
mechanics `scenarios.apply.apply_scenario` already implements. This is the smaller, lower-risk half
and is independently useful before Phase 2 exists.

**Phase 2 — the joint multi-period LP (Design A).** A new compiler
(`formulation/multi_period.py`) replicates every existing baseline LP component's exact
mathematical structure once per planning period, linked by a per-period transition identity, with
the objective jointly maximizing discounted revenue across the whole horizon. Reuses Phase 1's
event-timing/ordering primitive (`select_effective_events`) for exogenous per-period bound
construction — a *related*, not *identical*, reuse of Phase 1's own event-application mechanics
(see "Design A's own event handling" below for why).

### The shared refactor: `scenarios/apply.py`

Today `apply_scenario` does, inline:

```python
effective_events = sorted(
    (e for e in scenario.trade_events if e.effective_date <= baseline.effective_date),
    key=lambda e: (e.effective_date, _TYPE_PRIORITY[e.event_type], e.event_id),
)
# ... apply each event to inventory_by_id / routes_by_id ...
```

Split into two reusable pieces, promoted from private to package-shared (the same move
`formulation.compiler_support` already made for `resolve_component`/`set_route_bounds` when a
second compiler needed them):

```python
def select_effective_events(
    events: Sequence[TradeEvent], *, after: date | None, on_or_before: date
) -> list[TradeEvent]:
    """Section 13.3 step 3's deterministic order, generalized to an arbitrary window instead of
    always ``(-inf, baseline.effective_date]``."""
    ...

def apply_events(
    baseline: OptimizationRequest, events: Sequence[TradeEvent]
) -> tuple[OptimizationRequest, tuple[str, ...]]:
    """The existing per-event-type mutation loop (``_apply_trade_event``), unchanged, returning a
    new request rather than mutating local dicts `apply_scenario` then reassembles inline."""
    ...
```

`apply_scenario` becomes a thin, behavior-identical wrapper. **Its own existing 16 tests must keep
passing, unchanged, before either Phase 1's `settlement/` or Phase 2's `formulation/multi_period.py`
is written.**

### Recall-notice validation (shared by both designs)

New `validation/reconciliation.py::check_recall_notice_sufficiency(request)`, added to
`reconcile()`'s aggregation (so it runs uniformly for every request, before either design consumes
`known_future_events`):

```python
def check_recall_notice_sufficiency(request: OptimizationRequest) -> tuple[ValidationIssue, ...]:
    routes_by_id = {route.route_id: route for route in request.routes}
    issues: list[ValidationIssue] = []
    for idx, event in enumerate(request.known_future_events):
        if event.event_type is not TradeEventType.RECALL:
            continue
        route = routes_by_id.get(event.route_id)  # unresolved id already reported elsewhere
        if route is None:
            continue
        notice_days = (event.effective_date - event.trade_date).days
        if notice_days < route.recall_notice_days:
            issues.append(ValidationIssue(
                code="RECALL_NOTICE_INSUFFICIENT",
                message=(
                    f"known future RECALL {event.event_id!r} gives {notice_days} day(s) notice, "
                    f"less than route {event.route_id!r}'s recall_notice_days "
                    f"({route.recall_notice_days!r})"
                ),
                location=f"known_future_events[{idx}].effective_date",
            ))
    return tuple(issues)
```

Notice is measured `effective_date - trade_date` (when the recall takes effect, minus when it was
issued) against the route's own contractual minimum — not against `request.effective_date`, which
would conflate "how far in the future this is from today" with "how much notice the borrower
actually got."

## Phase 1 details (Design B — deterministic projection)

`settlement/project.py::project_multi_period`:

```python
def project_multi_period(
    request: OptimizationRequest, result: OptimizationResult, config: InventoryOptimizerConfig
) -> MultiPeriodProjection:
    settled = _settle_period_zero(request, result)          # REQ-005
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
    return _build_projection(request, states, boundaries, config, all_warnings, mode="projected")
```

`_settle_period_zero` builds period 0's state from `result.allocations`/`result.balances` directly
(the already-independently-verified post-solve numbers): each route's solved `post_quantity_shares`
becomes its `current_quantity_shares`; each inventory's `result.balances[i].post_on_loan_shares`/
`post_available_shares` become its own fields. This is also why Phase 1 never needs to know which
compiler produced `result` (REQ-012 for Phase 2 mirrors this same formulation-independence for
period 0's own solve).

## Phase 2 details (Design A — joint multi-period LP)

### Variables (REQ-009)

For a multi-period request, the plain `"q"`/`"inc"`/`"dec"`/`"a"` blocks used by
`compile_lp`/`compile_mip`/`compile_qp` are **not** used at all — `formulation/multi_period.py`
builds its own, entirely period-indexed blocks instead (empty `planning_periods` never reaches this
compiler at all — REQ-012):

```python
("q",   [f"{route.route_id}@{t:03d}"     for t in range(N + 1) for route in request.routes]),
("inc", [f"{route.route_id}@{t:03d}"     for t in range(N + 1) for route in request.routes]),
("dec", [f"{route.route_id}@{t:03d}"     for t in range(N + 1) for route in request.routes]),
("a",   [f"{inv.inventory_id}@{t:03d}"   for t in range(N + 1) for inv in request.inventory]),
```

`N = len(request.planning_periods)`; period 0 is included in the same period-indexed blocks (there
is no separate, non-indexed period-0 variable) — zero-padded to three digits for the same
lexicographic-order reason `specs/0009-discrete-fee-tier-pricing/plan.md` used for its own tier
index, and validated (not assumed) at ≤1000 periods, mirroring that spec's own cap.

### Rows, replicated per period `t` (REQ-009)

Reusing each existing component's exact structure, parameterized by period:

```text
inventory_balance[i]@t :  sum_j q_{j,t} + a_{i,t} = L_i,t - R_i,t - C_i,t
transition_identity[j]@t :  q_{j,t} - q_{j,t-1} = inc_{j,t} - dec_{j,t}
                             (q_{j,-1} := route.current_quantity_shares, i.e. period 0 is
                              *exactly* today's existing row, unchanged)
demand_cap[g]@t         :  sum_{j in J(g)} q_{j,t} <= D_g            (D_g constant across t — Non-Goal)
utilization_cap[...]@t, reserve_buffer[...]@t, counterparty_limit[...]@t : same pattern
```

`L_i,t`/`R_i,t`/`C_i,t` (period `t`'s own `total_lendable_shares`/`reserved_shares`/
`committed_out_shares`) and each route's period-`t` bounds (`maximum_quantity_shares`,
`hard_minimum_quantity_shares`, `eligible`) come from **Design A's own exogenous per-period bound
construction** — see below, not from `apply_events`.

### Design A's own event handling — related to, not identical to, Phase 1's reuse

`apply_events` (Phase 1) mutates a *fully-determined* snapshot: it needs a concrete
`current_quantity_shares` to compute a `RECALL`'s "forced reduction," because in the projection
there is no other decision-maker — the quantity is whatever it already was. In Phase 2, a route's
quantity at every period `t >= 1` is a **free decision variable** (`q_{j,t}`), not a fixed number,
so a `RECALL` cannot "force" a reduction the way `apply_events` computes it — it can only *tighten
the bound* `q_{j,t}` must respect, for every period on/after the recall's effective date, and let
the solver decide how `q_{j,t}` responds (subject to the tightened cap, exactly like every other
route bound today via `formulation.compiler_support.set_route_bounds`).

So Phase 2 introduces a small, distinct helper — `_period_bound_adjustments(request, boundaries)` —
that walks `known_future_events` using the *same* `select_effective_events` timing/ordering rule
Phase 1 uses, but accumulates **bound deltas** per period instead of mutating a snapshot:

```text
BUY/TRANSFER_IN  @ period t  ->  total_lendable_i delta for periods >= t
SELL/TRANSFER_OUT@ period t  ->  total_lendable_i delta for periods >= t (negative)
NEW_LOAN         @ period t  ->  route j's maximum_quantity_shares raised for periods >= t
RETURN           @ period t  ->  route j's maximum_quantity_shares/hard_minimum lowered for
                                   periods >= t (the route simply may not return to its old level)
RECALL           @ period t  ->  route j's maximum_quantity_shares lowered for periods >= t
                                   (same `new_max` formula `_apply_trade_event`'s RECALL branch
                                   already uses: `max(maximum_quantity_shares - qty,
                                   hard_minimum_quantity_shares)`), REQ-003's notice check already
                                   guarantees this is operationally honorable
```

This is recorded explicitly as a *related* reuse (same event semantics and ordering, same formulas
for the *bound* a given event implies) rather than a literal call to `apply_events`, because the two
have genuinely different jobs: mutate-a-snapshot vs. tighten-a-bound-on-a-free-variable (RISK-003).
A shared unit test (`test_settlement_project.py`/`test_multi_period_lp.py` both import the same
fixture-building helpers) pins that both designs agree on *what a given event means*, even though
they consume that meaning differently.

### Objective (REQ-011)

```text
maximize  sum_t  discount_factor_t * [ sum_j fee_revenue_coefficient(route_j, period_tau_t) * q_{j,t}
                                        - k+_j * inc_{j,t} - k-_j * dec_{j,t} ]

period_tau_t = (boundary_t - boundary_{t-1}).days / day_count_divisor    # generalizes T08's
                                                                          # existing tau, which
                                                                          # today only reads the
                                                                          # single scalar
                                                                          # planning_horizon_days
discount_factor_t = (1 + daily_discount_rate) ** -(boundary_t - effective_date).days
```

`fee_revenue_coefficient` itself (price, fee rate, revenue share, variable cost) is reused
unchanged — only the day-count fraction it is multiplied by becomes period-specific, since fee
rates/prices are held constant across the horizon (Non-Goals). This is a small, explicit
generalization of T08's existing formula, not a new one: at `N=0` (no periods), `period_tau_0`
would equal the config's own `planning_horizon_days`-based tau — but `N=0` never reaches this
compiler (REQ-012), so today's `compile_lp` path is never touched.

### Auto-routing and the MIP/QP conflict (REQ-012)

```python
def needs_multi_period(request: OptimizationRequest) -> bool:
    return bool(request.planning_periods)

def multi_period_conflict_issues(request, config) -> tuple[ValidationIssue, ...]:
    if not needs_multi_period(request):
        return ()
    if needs_mip(request) or needs_qp(config) or any(
        f.candidate_fee_rates for f in request.demand
    ):
        return (ValidationIssue(
            code="MULTI_PERIOD_MIP_QP_UNSUPPORTED",
            message=(
                "combining planning_periods with a MIP/QP-triggering route, policy, or fee-tier "
                "menu is not supported in the same compile -- disable one"
            ),
            location="request.planning_periods",
        ),)
    return ()
```

`facade.InventoryOptimizer.optimize()` gains one more branch, checked **before** the existing
MIP/QP dispatch: `if needs_multi_period(request): compile_multi_period_lp(...)`. This mirrors
exactly how `needs_mip`/`needs_qp` are already checked in sequence.

### Result unification (REQ-008)

Both `settlement.project.project_multi_period` (Phase 1) and `formulation.multi_period`'s own
result builder (Phase 2) construct the *same* `domain/settlement.py::MultiPeriodProjection` type,
differing only in `mode` (`"projected"` vs. `"jointly_optimized"`) and in how each period's
`PeriodBalance`/`PeriodEconomics` were derived (mechanical application vs. genuinely solved). A
desk-facing report never needs to know which compiler ran — only whether the periods it is reading
were decided or merely projected.

## Architecture & Components

```
domain/requests.py          + planning_periods, known_future_events (REQ-001, REQ-002)
validation/reconciliation.py + check_recall_notice_sufficiency (REQ-003)
domain/settlement.py         (new) PeriodBalance, PeriodEconomics, MultiPeriodProjection (REQ-008)
config/models.py            + MultiPeriodConfig.daily_discount_rate (REQ-007)
scenarios/apply.py           select_effective_events / apply_events promoted from private helpers

settlement/__init__.py       (new package)
settlement/project.py        (new) project_multi_period                      -- Phase 1

formulation/multi_period.py  (new) compile_multi_period_lp                    -- Phase 2
formulation/compiler_support.py + needs_multi_period, multi_period_conflict_issues
components/constraints/multi_period_balance.py  (new) period-indexed inventory_balance/
                                                  transition_identity/demand_cap/utilization_cap/
                                                  reserve_buffer/counterparty_limit row builders
components/objective_terms/multi_period_economics.py (new) discounted per-period fee_revenue/
                                                  transition_cost
facade.py                    + one more auto-routing branch (checked before MIP/QP)
```

No file under `solvers/`, `validation/solution_verifier.py` changes at all — Phase 2's
`CompiledProblem` is structurally identical in shape to today's (sparse matrix, bounds,
integrality-all-zero), so the existing HiGHS backend and independent verifier need no
multi-period-awareness of their own.

## Interfaces & Data Contracts

```python
# domain/requests.py additions (shared)
planning_periods: tuple[date, ...] = ()
known_future_events: tuple[TradeEvent, ...] = ()

# domain/settlement.py (new, shared by both designs)
class PeriodBalance(BaseModel):
    inventory_id: str
    period_index: int
    period_date: date
    total_lendable_shares: float
    on_loan_shares: float
    available_to_lend_shares: float
    utilization: float

class PeriodEconomics(BaseModel):
    period_index: int
    period_date: date
    day_count_fraction: float
    undiscounted_net_revenue_usd: float
    discount_factor: float
    discounted_net_revenue_usd: float

class MultiPeriodProjection(BaseModel):
    request_id: str
    mode: Literal["projected", "jointly_optimized"]     # REQ-008, NFR-003
    planning_periods: tuple[date, ...]
    balances: tuple[PeriodBalance, ...]
    economics: tuple[PeriodEconomics, ...]
    total_discounted_net_revenue_usd: float
    warnings: tuple[str, ...]
    disclosure: str        # varies by mode -- see below

# config/models.py addition
class MultiPeriodConfig(BaseModel):
    daily_discount_rate: float = Field(default=0.0, ge=0.0)
```

`disclosure` text depends on `mode`:

- `"projected"`: *"Period 0 is the solved allocation. Periods 1..N are a mechanical projection of
  already-known future events against that allocation, not a re-optimized plan."*
- `"jointly_optimized"`: *"Every period 0..N was jointly optimized against known future events;
  this is not a projection."*

## Constitution Check

| Principle | Upheld? | Notes |
| --- | --- | --- |
| P4 Correct by construction | yes | Period 0's rows are byte-identical to today's baseline formulas (not re-derived); Phase 2's PSD/global-optimality story is unchanged since it stays a continuous LP (NFR-005). |
| P5 Reversibility | yes | Both phases are additive-only; deleting `settlement/`, `formulation/multi_period.py`, the two request fields, and `MultiPeriodConfig` fully reverts this spec. |
| P6 Observability | yes | `MultiPeriodProjection.warnings`/`mode`/`disclosure` make both what happened and what kind of result it is unmissable. |
| P9 Security & data | yes | No new external data source. |

## Traceability Matrix

New `specs/spec002/TRACEABILITY.md` rows (no existing row covers §22.11/§22.12): `MPS-001`
(deterministic multi-period balance projection, §22.11, Phase 1), `MPS-002` (joint multi-period LP,
§22.11, Phase 2), `MPS-003` (recall-notice validation).

| ID | Evidence | Task |
| --- | --- | --- |
| REQ-001 | `domain/requests.py` fields + validators | T-001 |
| REQ-002 | Same validator | T-001 |
| REQ-003 | `validation/reconciliation.py::check_recall_notice_sufficiency` | T-002 |
| REQ-004 | `scenarios/apply.py::select_effective_events`/`apply_events`; `settlement/project.py` | T-003, T-004 |
| REQ-005 | `settlement/project.py::_settle_period_zero` | T-004 |
| REQ-006 | `settlement/project.py`'s `PeriodBalance` construction | T-004 |
| REQ-007 | `config/models.py::MultiPeriodConfig`; period-economics construction in both phases | T-005, T-004, T-009 |
| REQ-008 | `domain/settlement.py::MultiPeriodProjection` (+ `mode`) | T-005 |
| REQ-009 | `formulation/multi_period.py`; `components/constraints/multi_period_balance.py` | T-007, T-008 |
| REQ-010 | `formulation/multi_period.py::_period_bound_adjustments` | T-008 |
| REQ-011 | `components/objective_terms/multi_period_economics.py` | T-009 |
| REQ-012 | `formulation/compiler_support.py::needs_multi_period`/`multi_period_conflict_issues`; `facade.py` | T-006, T-010 |
| REQ-013 | `tests/golden/test_multi_period_settlement.py`, `tests/golden/test_multi_period_lp.py` | T-011, T-012 |
| NFR-001 | Full existing suite (239, pre-this-spec) unchanged | T-011, T-012 |
| NFR-002 | No calendar dependency; documented simplification | spec.md Non-Goals |
| NFR-003 | `mode`/`disclosure`, unconditional | T-005 |
| NFR-004 | `ScenarioApplicationError` reuse (Phase 1); existing solver-status/verification machinery (Phase 2) | T-004, T-007 |
| NFR-005 | Existing HiGHS LP status normalization, unchanged | T-007 |

## Trade-offs & Alternatives

**Both designs, sequenced, vs. either alone (owner-confirmed 2026-09-07):** shipping only the
projection would leave the desk unable to ask "should I lend less today because of a recall I
already know about" — only able to see its consequence after the fact. Shipping only the joint LP
without the projection first would mean the larger, higher-risk piece lands with no smaller,
independently-useful, easier-to-validate increment along the way, and no shared, already-tested
event-timing primitive to build it on. Sequencing (Phase 1 fully done and tested before Phase 2
begins) captures the benefit of "both" while keeping the riskier half's blast radius contained and
reviewable on its own (RISK-005).

**`apply_events` reuse (mutate-a-snapshot) vs. a from-scratch bound-adjustment function for Phase
2:** considered literally reusing `apply_events` for Phase 2 too (apply events to a synthetic
period-`t` "as if already decided" snapshot, then read off the resulting bounds) — rejected because
it would require inventing a fake `current_quantity_shares` for a variable the solver has not yet
decided, which is either wrong (biases the solver toward whatever fake value was chosen) or
meaningless. The bound-adjustment function is a distinct implementation but reuses the *same event
semantics and formulas*, and a shared fixture-building test pins that both designs agree on what
each event type means (see Phase 2 details above).

**A new `Formulation` enum value vs. a wholly separate compiler module:** chose a separate module
(`formulation/multi_period.py`) without touching the `Formulation` enum (`LP`/`MIP`/`QP` stay as
they are) since Phase 2's `CompiledProblem` is structurally an LP (no integrality, no quadratic
term) — `Formulation.LP` remains an accurate tag for what HiGHS receives; multi-period-ness is a
property of the *request* (`planning_periods` non-empty), not a new mathematical formulation kind
the solver backend needs to know about.

**Excluding MIP/QP from Phase 2's V1 (REQ-012) vs. supporting them from the start:** every prior
phase in this repo built its baseline capability before combining it with the next (LP before MIP,
MIP before QP, each independently gated and each new combination explicitly fails closed until
supported). Phase 2 follows the identical discipline rather than attempting MIP+QP+multi-period
all at once.

## Validation Strategy

- `tests/unit/test_scenario_apply.py` (existing, T13-T14) — must keep passing unchanged after the
  `select_effective_events`/`apply_events` extraction, before any new code is layered on top.
- `tests/unit/test_domain_contracts.py` additions — `planning_periods`/`known_future_events` field
  validation (AC-002).
- `tests/unit/test_reconciliation.py` (or equivalent) additions — `check_recall_notice_sufficiency`
  (AC-003).
- `tests/golden/test_multi_period_settlement.py` — Phase 1's worked fixture (AC-004/AC-005).
- `tests/unit/test_settlement_project.py` — Phase 1 boundary/ordering unit tests; formulation-
  independence of period 0 (works whether it was solved via LP, MIP, or QP).
- `tests/golden/test_multi_period_lp.py` — Phase 2's worked fixture (AC-006), proving period-0
  allocation genuinely differs from the single-period optimum.
- `tests/unit/test_multi_period_lp_compiler.py` — Phase 2 row/coefficient shape, the MIP/QP
  conflict rejection (AC-007), `mode`/`disclosure` (AC-008).
- A `slow`-marked scale test sizing Phase 2's route × period growth (RISK-004), following
  `specs/0005-test-hardening/`'s benchmark precedent.
- Full suite rerun (AC-001/NFR-001) after each phase.

### Worked fixture sketch — Phase 1 (Design B)

One inventory (`INV-1`, 100 lendable shares, `price_usd=10.0`), one route (`RT-A`, solved to fill
its full 100 shares at period 0, `fee_rate=0.02`, `revenue_share=1.0`, `variable_cost_rate=0.0`,
`recall_notice_days=1`), `act_360`/`planning_horizon_days=1`, `daily_discount_rate=0.0`.
`planning_periods = (effective_date + 1 day, effective_date + 3 days)`; `known_future_events`
contains one `RECALL` (`route_id=RT-A`, `quantity_shares=40`, `trade_date=effective_date`,
`effective_date=effective_date + 3 days` — 3 days' notice, satisfying `recall_notice_days=1`).
Expected: period 1 equals period 0 exactly (no event lands in `(effective_date, +1]`); period 2's
`on_loan_shares` drops `100 -> 60`, `available_to_lend_shares` rises `0 -> 40`. Each period's own
`day_count_fraction` is the gap *from the previous period boundary*, not a fixed constant: period
1 spans 1 day (`effective_date` to `effective_date+1`), period 2 spans 2 days
(`effective_date+1` to `effective_date+3`) -- period 0 itself uses the config's own
`planning_horizon_days` (today's existing single-period `tau`), matching `result.economics`
exactly. Period 2's undiscounted revenue = `10.0 * (2/360) * 0.02 * 60 = 0.0667` (the post-recall
quantity, over its own 2-day period length).

### Worked fixture sketch — Phase 2 (Design A)

Same route/inventory shape, but now solved *jointly* across `(effective_date, effective_date + 1
day)` with a known future `RECALL` of 100 shares (the *entire* position) effective in period 1,
`recall_notice_days=1`, `trade_date=effective_date` (exactly the minimum notice — passes REQ-003).
Add an `increase_cost_usd_per_share` large enough that re-lending after a forced recall is costly
(e.g. `0.01`). A single-period-only optimizer (blind to period 1) would lend the full 100 at period
0; the joint LP, seeing period 1's forced recall and the cost of the resulting `dec` at period 1
plus zero ability to re-lend before the horizon ends, should instead lend less at period 0 if doing
so raises the two-period discounted total versus lending 100 and eating the forced `dec`. The exact
break-even quantity is computed by hand in the test from the two periods' discounted coefficients,
never pasted from a solve, matching the convention `specs/0006`-`0009` all used.

## Rollout, Observability & Rollback

Both phases are additive-only. Rollback is deleting `settlement/`, `formulation/multi_period.py`,
`components/constraints/multi_period_balance.py`, `components/objective_terms/
multi_period_economics.py`, the two request fields, `MultiPeriodConfig`, and the new validation
check. No existing module's behavior changes for any request that leaves `planning_periods` empty
(NFR-001). Observability is `MultiPeriodProjection.warnings`/`mode`/`disclosure`.

## Open Questions

- Whether a future spec should let fee rates/prices vary per period within `known_future_events`
  (spec.md Non-Goals) — deferred until a real desk need exists.
- Whether MIP/QP business rules should eventually compose with Phase 2 (REQ-012's current
  exclusion) — deferred; no desk need identified yet.
