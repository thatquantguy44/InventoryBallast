# Plan: Discrete fee-tier pricing (joint fee/quantity, Phase 5 item 1)

- **Spec:** 0009-discrete-fee-tier-pricing (`spec.md`)
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code)
- **Last updated:** 2026-09-05

> HOW. This plan requires an approved `spec.md`. Every requirement in the spec
> must appear in the traceability matrix below.

## Approach

Follow `specs/0006-mip-business-rules/`'s pattern exactly: new optional domain field → new
`BuildContext`-computed sets and variable blocks (empty when unused) → new MIP-only components →
`needs_mip` extension so the existing facade dispatch and `compile_lp` rejection both pick it up
for free. No new compiler, no new solver capability, no new formulation enum — a tiered request is
just a MIP request.

## Notation

For demand group `g` with candidate fees `f_g1 < f_g2 < ... < f_gK` and routes `j ∈ J(g)`:

| Symbol | Meaning | Source |
| --- | --- | --- |
| `f_gk` | candidate fee `k` | new `DemandForecast` field (REQ-001) |
| `D_gk` | demand at that fee | `evaluate_demand_cap(forecast_g, f_gk, config).effective_cap_shares`, precomputed (REQ-002) |
| `f_j^ref` | incumbent borrower fee | existing `route.fee_rate` (uniform per group, already validated) |
| `s_j`, `v_j` | revenue share, variable cost rate | existing `LoanRoute` fields |
| `P_i`, `tau` | price, day-count fraction | existing, via `fee_revenue_coefficient` |
| `z_gk ∈ {0,1}` | tier selected | new variable, kind `"t"` |
| `w_jk >= 0` | route `j`'s quantity at tier `k` | new variable, kind `"w"` |
| `q_j` | route post-quantity | existing |

## Constraints (REQ-004)

Three row families, all only for tiered groups:

```text
(1) tier_select[g]     :  sum_k z_gk <= 1
(2) tier_capacity[g,k] :  sum_{j in J(g)} w_jk - D_gk * z_gk <= 0
(3) tier_split[j]      :  q_j - sum_k w_jk = 0
```

Row (2) does double duty — it caps quantity at the tier's own demand *and* forces `w_jk = 0`
whenever `z_gk = 0`, so no separate big-M linking row is needed. Row (1) is `<=` not `=` (spec.md's
Assumptions): a group whose every tier is uneconomic simply goes unselected with all `w_jk = 0`,
which row (3) then forces `q_j = 0` — "don't lend to this borrower at any offered price" stays
feasible rather than becoming infeasible.

**`demand_cap` must skip tiered groups (REQ-010).** Its existing row is
`sum_j q_j <= D_g(f^ref)` — the demand at the *incumbent* fee. If a cheaper tier is selected,
demand is genuinely higher (`D_gk > D_g(f^ref)` for `f_gk < f^ref`), and leaving that row in place
would silently cap the very volume the repricing was meant to win. Row (2) is the correct cap for
these groups. The skip is one guarded line, inert whenever no group has tiers.

## Objective: contribute the delta, leave `fee_revenue` alone (REQ-005, NFR-003)

The existing `fee_revenue` term already contributes `c_j^ref * q_j` for every route, where
`c_j^ref = P_i * tau * (f_j^ref * s_j - v_j)`. Rather than teach it about tiers, the new term
contributes only the difference between the selected tier and the incumbent:

```text
c_jk = P_i * tau * (f_gk * s_j - v_j)          # revenue coefficient at tier k
delta_jk = c_jk - c_j^ref = P_i * tau * s_j * (f_gk - f_j^ref)
```

The variable-cost term cancels, leaving a coefficient that is trivially checkable by hand. Because
row (3) guarantees `sum_k w_jk = q_j`:

```text
c_j^ref * q_j  +  sum_k delta_jk * w_jk   ==   sum_k c_jk * w_jk
\_____________/    \____________________/       \_______________/
 fee_revenue          new pricing term           what §12.4 asks for
```

So the total is exactly §12.4's `f_gk * q_gk` valuation, route-by-route, with `fee_revenue`
untouched. `attribute()` recomputes `sum_{j,k} delta_jk * w_jk` from primal values with
`baseline_value_usd = 0.0` — at the incumbent price the delta is zero by construction, matching how
`transition_cost` and `allocation_stability` already report a zero baseline.

### Deviation from §12.4's sketch, recorded

§12.4 writes the tier quantity as a single group-level `q_gk` and the objective as `f_gk * q_gk`.
This plan uses per-route `w_jk` instead, because §12.2 states in the same specification that
"Lender revenue shares may still produce different net route economics" — routes in one demand
group share a borrower and security but can sit on different inventory pools with different `s_j`
and `v_j`. A single group-level revenue coefficient would be wrong for any such group. The
group-level quantity remains recoverable as `q_gk = sum_j w_jk`, which is what row (2) already
sums, so nothing in §12.4's structure is lost — only refined. AC-010 pins this behavior.

## Variables and index stability (REQ-003, REQ-008, NFR-001)

Two new blocks appended **after** every existing block (`q`, `inc`, `dec`, `a`, `z`, `n`):

```python
("t", [f"{group_id}#{k:03d}" for tiered groups g, k in range(K_g)]),
("w", [f"{route_id}#{k:03d}" for routes j in tiered groups, k in range(K_g)]),
```

Both lists are empty for an untiered request, and `build_variable_index` contributes zero keys for
an empty block — so `q`/`inc`/`dec`/`a` positions are unchanged, exactly the property
`specs/0006-mip-business-rules/` verified for `z`/`n` (AC-009).

Two details that matter:

- **Zero-padded tier index.** `build_variable_index` sorts each block's scope ids lexicographically,
  so an unpadded `"RT-A#10"` would sort between `"RT-A#1"` and `"RT-A#2"`. Padding to three digits
  keeps lexicographic order equal to numeric order (and caps a group at 1000 tiers, which is far
  past any plausible fee ladder — validated, not assumed).
- **Reserved separator.** `VariableKey.scope_id` is a single string, so `(route, tier)` must be
  encoded. `"#"` is the separator, and the new component's `validate()` returns a structured issue
  for any route id or demand-group id containing it, rather than emitting an ambiguous key
  (REQ-008/AC-008). Fail closed, in keeping with how every other ambiguity in this repo is handled.

## `BuildContext` additions (REQ-002)

```python
tiered_demand_group_ids: frozenset[str]
tier_caps: Mapping[str, tuple[EvaluatedDemand, ...]]   # group_id -> one per candidate fee, in order
```

`build_context` fills `tier_caps` by calling the **unchanged** `evaluate_demand_cap` once per
candidate fee — the same call it already makes once per group today. Elasticity remains
preprocessing (§12.1); nothing about the curve becomes an LP decision.

## Routing (REQ-006)

`needs_mip(request)` gains `or any(forecast.candidate_fee_rates for forecast in request.demand)`,
and `mip_required_issues` gains one issue per tiered group
(`location=f"demand[{i}].candidate_fee_rates"`). That single change makes `compile_lp` fail closed
and `facade.InventoryOptimizer.optimize` route to `compile_mip` automatically — both mechanisms
already exist and neither needs editing. `compile_mip`'s `MIP_CONSTRAINTS` gains the new constraint
component; a new `MIP_OBJECTIVES` tuple carries the pricing term.

## Result reporting (REQ-007, §14.3's disclosure duty)

A new frozen model plus one additive, defaulted section:

```python
class PricingSelection(BaseModel):
    demand_group_id: str
    reference_fee_rate: float                 # the incumbent, for comparison
    candidate_fee_rates: tuple[float, ...]    # the menu that was actually offered
    selected_fee_rate: float | None           # None when no tier was selected
    selected_tier_index: int | None
    filled_shares: float

# OptimizationResult gains:
pricing: tuple[PricingSelection, ...] = ()
```

Defaulted to empty, so every existing result and test is unaffected. This is what §14.3's "records
breakpoints ... and whether SOS/integer variables were introduced" reduces to here: the breakpoints
*are* the candidate fees, and the integer variables are already visible through
`CompiledProblem.integrality` and the component manifest. Deliberately **not** included: any
distance-to-continuous-optimum figure — computing it requires solving the continuous nonlinear
problem this spec exists to avoid (spec.md Non-Goals).

## Constitution Check

- Spec is source of truth: `spec.md` written first; §12.4 is the normative formulation being built.
- Traceable: every REQ/NFR maps to file(s) and test(s) below.
- Definition of Done: each AC has a named test.
- Correct by construction: the model stays a linear MIP, so global optimality is provable rather
  than assumed (NFR-002); ambiguous composite keys are rejected rather than encoded (REQ-008).
- No silent trade-offs: the §12.4 deviation, the `demand_cap` skip, the delta-revenue construction,
  the `<=` vs `=` tier row, and the omitted error bound are each recorded with reasoning.

## Traceability Matrix

| ID | Evidence | Task |
| --- | --- | --- |
| REQ-001 | `domain/demand.py::DemandForecast.candidate_fee_rates` + validator | T-001 |
| REQ-002 | `formulation/context.py::build_context` (`tier_caps`, `tiered_demand_group_ids`) | T-002 |
| REQ-003 | `formulation/context.py`'s `"t"`/`"w"` variable blocks | T-002 |
| REQ-004 | `components/constraints/fee_tiers.py::FeeTierConstraint` | T-003 |
| REQ-005 | `components/objective_terms/tier_pricing.py::TierPricingTerm` | T-004 |
| REQ-006 | `formulation/compiler_support.py::needs_mip`, `mip_required_issues`; `formulation/mip.py`'s component tuples | T-005 |
| REQ-007 | `domain/results.py::PricingSelection`; `reporting/result_builder.py` | T-006 |
| REQ-008 | `FeeTierConstraint.validate` separator check | T-003 |
| REQ-009 | `tests/golden/test_fee_tier_pricing.py` | T-008 |
| REQ-010 | `components/constraints/demand.py` (tiered-group skip) | T-003 |
| NFR-001 | Full existing 193-test suite; `tests/unit/test_fee_tier_compiler.py`'s index-stability test | T-008 |
| NFR-002 | Existing status normalization, unchanged; golden tests assert `OPTIMAL` | T-008 |
| NFR-003 | `fee_revenue` diff is empty; `demand_cap`'s diff is the single guarded skip | T-003, T-008 |
| NFR-004 | `PricingSelection`'s menu-plus-selection shape; AC-005's test | T-006, T-008 |

## Trade-offs & Alternatives

- **Per-route `w_jk` vs. group-level `q_gk`** — see the recorded deviation above. Group-level is
  literally what §12.4 sketches and uses fewer variables, but is wrong whenever routes in a group
  differ in `revenue_share`/`variable_cost_rate`, which is normal across inventory pools.
- **Delta revenue vs. modifying `fee_revenue`** — modifying `fee_revenue` to skip tiered routes and
  adding a full-value tier term would work identically, but touches a component every existing
  golden test depends on, and splits one economic concept across two code paths. The delta keeps
  `fee_revenue` untouched *and* yields a more readable attribution ("revenue at today's price, plus
  what repricing added"). Cost: two attribution lines instead of one for tiered groups.
- **`sum_k z_gk <= 1` vs. `= 1`** — equality would force a price to be chosen even when every tier
  loses money, converting a business "don't trade" into an infeasibility or a forced loss.
- **Tiers on `DemandForecast` vs. a new standalone schedule object** — a standalone
  `PricingSchedule` would match §9.6's schedule-envelope pattern (versioned, effective-dated,
  approval-bearing), but no schedule subsystem exists yet (T29, unstarted). Putting candidates on
  the forecast that already owns `reference_fee_rate` and `elasticity` keeps this spec independent
  of T29; migrating to a schedule later is additive.

## Validation Strategy

- `tests/golden/test_fee_tier_pricing.py` — repricing up (AC-001), repricing down for volume
  (AC-002), incumbent wins and matches the untiered objective (AC-003), attribution reconciliation
  and hand-computed delta (AC-006), reporting shape (AC-005), differing `revenue_share` across
  routes in one group (AC-010). Fixtures are hand-constructed and reasoned through here, since
  `EXAMPLES.md` has no worked pricing case (E1-E9 cover none) — the same approach `0006`/`0007`
  used.
- `tests/unit/test_fee_tier_compiler.py` — exact row/coefficient shape for all three row families,
  `compile_lp` rejection (AC-004), separator rejection (AC-008), and an untiered request producing
  byte-identical variable/row indexes to `compile_lp`'s (AC-009).
- `tests/unit/test_domain_contracts.py` additions — tier field validation (AC-007).
- A `slow`-marked scale test sizing `J*K` growth (RISK-001), following
  `specs/0005-test-hardening/`'s benchmark precedent.
- Full suite rerun (AC-009/NFR-001).

### Worked fixture sketch (for the golden tests)

One group, one route, `P_i = 10.0`, `tau = 1/360`, `s_j = 1.0`, `v_j = 0`, incumbent
`f^ref = 0.036`, constant-elasticity curve with `Q_ref = 100`, `F_ref = 0.036`, and candidate tiers
`{0.018, 0.036, 0.072}`. Unconstrained revenue `P*tau*f*D(f)`, computed exactly:

| `epsilon` | fee 0.018 | fee 0.036 | fee 0.072 | winner |
| --- | --- | --- | --- | --- |
| 0.5 | D=141.42, rev=0.0707 | D=100.00, rev=0.1000 | D=70.71, rev=**0.1414** | highest tier (AC-001) |
| 1.0 | D=200.00, rev=0.1000 | D=100.00, rev=0.1000 | D=50.00, rev=0.1000 | exactly indifferent |
| 2.0 | D=400.00, rev=**0.2000** | D=100.00, rev=0.1000 | D=25.00, rev=0.0500 | lowest tier (AC-002) |

**The `epsilon = 2.0` fixture only tests what it claims if supply is ample.** Its winning tier wants
400 shares; with the usual 100-share fixture inventory the supply cap binds at every tier and the
ranking *inverts* — 0.018 yields `(10/360)*0.018*100 = 0.005`, 0.036 yields `0.01`, and 0.072 yields
`(10/360)*0.072*25 = 0.005`, so the incumbent wins for supply reasons rather than pricing reasons. A
"repricing down wins" test built on 100 shares would therefore pass for the wrong reason or fail
confusingly. Give AC-002's fixture at least 400 lendable shares.

That inversion is itself the natural **AC-003 ("incumbent wins")** fixture: `epsilon = 2.0` with 100
shares of supply is a realistic scarce-name case where cutting price cannot buy volume that does not
exist and raising it sheds more demand than it gains — the model should hold at `0.036`.

Unit elasticity (`epsilon = 1.0`) is worth keeping as a third case precisely because it is exactly
revenue-neutral: it proves the formulation does not manufacture a preference where the economics are
genuinely indifferent (any tier is optimal; assert on the objective value, not on which tier).
Expected values are recomputed in the tests from these formulas, never pasted from a solve.

## Rollout, Observability & Rollback

Additive throughout except two guarded lines (`demand_cap`'s skip, `needs_mip`'s clause), both
inert without tiers. Rollback is deleting the new components/field/section and reverting those two
lines. Observability is `PricingSelection` in every result plus the attribution's own pricing line.
`specs/engine_spec/TRACEABILITY.md`'s `LP-004` gains discrete-pricing evidence and `LP-009` gains the
§12.4/§14.1-seventh-trigger portion; both notes stay honest about what remains (continuous
nonlinear pricing, PWL interpolation, NLP backend).

## Open Questions

- Whether a `REPRICED_TO_TIER` reason code should join `ReasonCode`'s 24 values, or whether the
  structural `PricingSelection` section is sufficient (spec.md's Open Questions). Proposed:
  structural first.
- Whether tiers should eventually migrate from `DemandForecast` to a versioned, approval-bearing
  pricing schedule once T29 lands — additive when it happens.
