# Plan: Expected economics and entity-hierarchy realism (Realism release R1)

- **Spec:** 0012-expected-economics-realism (`spec.md`)
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code)
- **Last updated:** 2026-09-15

> HOW. This plan requires an approved `spec.md`. Every requirement in the spec must appear in the
> traceability matrix below.

**Resolved (2026-09-15):** shadow/compare mode is the default; T24's PWL unwind cost is deferred to
its own spec; and the §22.9 fail-closed rule stands, narrowed to hard entity-scoped limits, gated on
internal approval rather than vendor confidence, with no conservative-inclusion escape hatch. The
Slice A section below reflects those decisions and differs materially from its first draft.

## Approach

Three independent slices, each extending a structure that already exists rather than introducing a
new one. They share only `BuildContext` as a delivery slot and can be implemented, reviewed, and
reverted separately:

| Slice | Extends | New machinery |
| --- | --- | --- |
| A — entity hierarchy (T22) | `counterparty.py`'s route-scope lookup | none |
| B — expected economics (T23) | `fee_revenue_coefficient()`'s one formula | none |
| C — dynamic buffer (T24, buffer half) | `ReserveBufferConstraint`'s `max(...)` | none |

Every new input is optional and absent by default; the default `economics_mode` is `contractual`.
With nothing supplied the compiled problem is byte-identical to today (NFR-001) — the same
zero-cost-when-absent property `0006`'s `z`/`n` blocks, `0009`'s tier blocks, `0010`'s
calendar-free settlement, and `0011`'s enrichment mappings each hold.

## Slice A — entity hierarchy (REQ-001 through REQ-006)

```python
class EntityRelationship(BaseModel):          # domain/reference.py, beside SecurityReference
    entity_id: str                            # the borrower/counterparty as the book knows it
    legal_entity_id: str
    ultimate_parent_id: str
    relationship_type: str
    ownership_confidence: float               # 0.0-1.0 -- the VENDOR's score. Screens; never authorizes.
    approval_reference: str | None = None     # internal credit/legal approval. This is the authority.
    # effective interval + provenance come from the PointInTimeValue envelope, not duplicated here
```

Carried as `PointInTimeValue[EntityRelationship]`, resolved by
`enrichment/entity_hierarchy.py::resolve_hierarchy(borrower_id, relationships, *, as_of,
known_as_of)`, which delegates candidate selection to `0011`'s
`enrichment.point_in_time.resolve_latest_known` **unchanged**. That delegation is the whole
no-look-ahead story for Slice A (AC-006): there is no second time-resolution implementation to keep
honest.

`CounterpartyLimit` gains two optional scope fields alongside today's `borrower_id`:

```python
    legal_entity_id: str | None = None
    ultimate_parent_id: str | None = None
```

`components/constraints/counterparty.py` today resolves
`context.routes_by_borrower.get(limit.borrower_id, ())`. It gains one branch: when a limit carries
an entity scope, its route set is the union over every borrower resolving into that entity, taken
from a new `BuildContext.routes_by_entity`/`routes_by_ultimate_parent` mapping computed once in
`formulation/context.py` (the same slot `routes_by_borrower` already occupies). The row itself —
`sum(P_i * q_j) <= K` — is unchanged; only its membership widens. §22.9's two summations are
therefore the existing notional and quantity rows at a wider scope, not new row families.

**Fail-closed (REQ-004, REQ-005, REQ-006).** A mapping is **usable for hard aggregation only when
it carries an `approval_reference`.** `ownership_confidence` never authorizes — it is reported, and
may drive a warning below a configured `ValidationConfig.minimum_entity_confidence`, but an
unapproved 0.99 mapping is unusable and an approved 0.40 mapping is usable. §22.9 puts it directly:
Bloomberg "can propose the hierarchy, but internal credit/legal owners approve." Resolution
therefore yields one of four states:

| State | Meaning | Issue code |
| --- | --- | --- |
| usable | approved mapping resolves | — |
| unapproved | mapping resolves, no `approval_reference` | `ENTITY_MAPPING_UNAPPROVED` |
| conflicting | two relationships effective at once naming different parents | `ENTITY_MAPPING_CONFLICT` |
| missing | nothing resolves for this borrower | `ENTITY_MAPPING_UNRESOLVED` |

**Where the rejection bites (REQ-005).** Not every unusable mapping stops the run — §22.9's
qualifier is "fail closed *for hard aggregation*":

```text
for each borrower with an unusable mapping:
    if borrower has no routes that could be allocated (all ineligible / zero max):
        no issue                       # contributes to no sum; cannot breach anything
    elif state is unapproved or conflicting:
        fail iff a hard entity-scoped limit names the candidate parent(s)
    elif state is missing:
        fail iff the request contains ANY hard entity-scoped limit
        # absence cannot prove the borrower falls outside a group
```

A non-`hard` entity-scoped limit degrades to a warning instead, reusing `0011`'s warnings idiom —
that is the sanctioned way to say "track group exposure advisorily." Unusable mappings are surfaced
in the result either way: §22.9 asks for the failure *and* the data-quality disclosure, not one or
the other.

**Why never "warn and continue" for a hard limit.** An unresolved borrower simply falls out of the
parent's `sum`, so the row silently *relaxes* — missing data defaults to omission, and omission is
the permissive direction. Worse, `validation.solution_verifier` recomputes rows from
`CompiledProblem` and would report `verification.passed` for a row missing terms it was never told
about: the independent verifier checks arithmetic, not intent, and structurally cannot catch this.
It has to be caught at validation time or not at all. **No conservative-inclusion escape hatch is
built** (`spec.md` Non-Goals): it is undefined for the missing case, it can convert a clear
rejection into a murkier infeasibility, and `hard = False` already expresses "let the run survive"
honestly.

## Slice B — expected economics (REQ-007 through REQ-013)

```python
class ExpectedEconomics(BaseModel):           # domain/economics.py (new)
    route_id: str
    take_up_probability: float                # 0.0-1.0
    conditional_expected_days_active: float   # > 0
    return_hazard: float | None = None
    repricing_hazard: float | None = None
    recall_failure_probability: float | None = None
    manufactured_payment_cost_usd: float = 0.0
    indemnification_capital_cost_usd: float = 0.0
    settlement_fail_cost_usd: float = 0.0
    relationship_value_or_cost_usd: float = 0.0
    model_version: str                        # §22.5: every coefficient carries these three
    calibration_date: date
    uncertainty: float
```

`formulation/context.py` precomputes, per route (REQ-008):

```text
expected_active_fraction_j = clamp(
    take_up_probability_j * conditional_expected_days_active_j / planning_horizon_days, 0.0, 1.0
)
```

and exposes `BuildContext.expected_active_fractions` / `expected_costs`. Elasticity's precedent
holds exactly: computed once, before model construction, never during it (NFR-003).

**The coefficient (REQ-009).** `fee_revenue_coefficient` gains one optional parameter, mirroring
how `0010` added `day_count_fraction`:

```python
def fee_revenue_coefficient(route, inventory, formulation_config, *,
                            day_count_fraction=None, expected_active_fraction=None) -> float:
    tau = ...                                   # unchanged
    contractual = inventory.price_usd * tau * (
        route.fee_rate * route.revenue_share - route.variable_cost_rate
    )
    if expected_active_fraction is None:        # every existing call site
        return contractual
    return contractual * expected_active_fraction
```

`None` at every existing call site is what makes NFR-001 structural rather than tested-hopefully.
Because `contribute()`, `attribute()`, `validation.solution_verifier`'s objective reconstruction,
and `reporting.explanations` all already route through this function, expected mode reaches all
four without four edits — and NFR-002's attribution reconciliation follows by construction.

**What the factor does and does not multiply (RISK-004, pinned here deliberately):** it scales the
**fee-revenue term only**. It does **not** scale `transition_cost` (an increase or decrease is paid
when the trade happens, regardless of how long the loan then survives), and it does **not** scale
the additive expected cost coefficients below, which are already expectations in their own right.
The additive costs enter as a separate per-route linear objective contribution:

```text
-(manufactured_payment_cost_usd + indemnification_capital_cost_usd
  + settlement_fail_cost_usd - relationship_value_or_cost_usd) per share on q_j
```

carried by a new `objective_terms/expected_costs.py` component rather than folded into
`fee_revenue`, so attribution reports them as their own line (§18.2's per-component reconciliation
stays meaningful).

**Mode switch (REQ-010) and shadow mode (REQ-011).**

```python
class ObjectiveConfig(BaseModel):
    allocation_stability_penalty: float = 0.0
    economics_mode: Literal["contractual", "expected"] = "contractual"
```

- `contractual` (default): the compiled objective is exactly today's. If estimates are supplied,
  `facade.optimize()` additionally computes — post-solve, from the *already-solved* quantities —
  what the expected economics of that same allocation would be, and attaches it as a comparison
  section. **No coefficient, bound, or allocation changes.** This is deliberately the same shape as
  `0010`'s projection: report against a solved result rather than re-optimizing.
- `expected`: `expected_active_fraction` reaches the coefficient, allocations genuinely differ, and
  every route must carry an `ExpectedEconomics` record or compilation fails closed (REQ-012) —
  mixing expected and contractual coefficients across routes in one objective would make the
  objective uninterpretable.

**Disclosure (REQ-013).** A new defaulted `OptimizationResult.economics` section names the mode and
lists, per route, `model_version` / `calibration_date` / `uncertainty` for each estimate used, plus
the shadow comparison when present. Additive and defaulted, so no existing result or test changes
— the same additive-section pattern `0009`'s `pricing` and `0011`'s warnings already follow.

## Slice C — dynamic buffer (REQ-014 through REQ-016)

```python
class DynamicBuffer(BaseModel):               # domain/economics.py
    inventory_id: str
    legal_minimum_shares: float = 0.0
    pending_settlement_need_shares: float = 0.0
    demand_uncertainty_quantile_shares: float = 0.0
    event_recall_buffer_shares: float = 0.0
    liquidity_horizon_buffer_shares: float = 0.0
    source: str
    source_version: str
```

`ReserveBufferConstraint.contribute` today computes `buffer = max(buffer,
policy.reserve_buffer_shares, policy.reserve_buffer_fraction * total_lendable)` across applicable
policies and sets `a_i`'s lower bound. §22.7's `required_buffer_i = max(legal_minimum,
pending_settlement_need, demand_uncertainty_quantile, event_recall_buffer,
liquidity_horizon_buffer)` folds into that same `max` as five more candidates. Because the buffer is
precomputed, "the default remains an LP" (§22.7, verbatim) — NFR-005 holds without argument.

REQ-016's binding-component report means tracking *which* candidate won the `max`, not just its
value; this is a `max` over `(value, label)` pairs and lands in the result's existing constraint
surface.

## Constitution Check

- **Spec is the source of truth:** every REQ/NFR traces to §22.5, §22.7, §22.9, §25's R1
  definition, or §26's T22-T24 grouping.
- **No orphan code:** no `ports/liquidity_data.py` or PWL scaffolding for work this spec does not
  do; Slice C's buffer is consumed the day it lands.
- **Correct by construction:** no-look-ahead is inherited from `0011` rather than reimplemented
  (REQ-002); attribution consistency is structural via one shared coefficient function (REQ-009).
- **Honest reporting:** `expected` mode is off by default, disclosed when on, and G3 is explicitly
  not granted by anything here (NFR-004). Shadow mode reports both numbers rather than replacing
  one with the other.
- **No silent trade-offs:** the PWL deferral, the shadow-vs-expected default, the fail-closed
  entity rule, and the R-numbering defect are all raised as open questions, not decided quietly.

## Traceability Matrix

| Requirement | Plan section | Test(s) (see `tasks.md`) |
| --- | --- | --- |
| REQ-001 | Slice A — `EntityRelationship` | `test_domain_entity.py` |
| REQ-002 | Slice A — resolver | `test_entity_hierarchy.py` |
| REQ-003 | Slice A — limit scope | `test_entity_limits.py` |
| REQ-004 | Slice A — fail-closed (approval authorizes) | `test_entity_limits.py` |
| REQ-005 | Slice A — where the rejection bites | `test_entity_limits.py` |
| REQ-006 | Slice A — non-hard degrades to a warning | `test_entity_limits.py` |
| REQ-007 | Slice B — `ExpectedEconomics` | `test_domain_economics.py` |
| REQ-008 | Slice B — precomputed factor | `test_expected_economics_context.py` |
| REQ-009 | Slice B — the coefficient | `test_expected_economics.py` |
| REQ-010 | Slice B — mode switch | `test_expected_economics.py` |
| REQ-011 | Slice B — shadow mode | `test_expected_economics.py` |
| REQ-012 | Slice B — fail closed on partial estimates | `test_expected_economics.py` |
| REQ-013 | Slice B — disclosure | `test_expected_economics.py` |
| REQ-014 | Slice C — `DynamicBuffer` | `test_domain_economics.py` |
| REQ-015 | Slice C — the `max` | `test_dynamic_buffer.py` |
| REQ-016 | Slice C — binding component | `test_dynamic_buffer.py` |
| REQ-017 | Golden tests | `tests/golden/test_expected_economics.py` |
| NFR-001 | Every slice's absent-default | full-suite regression; byte-identical index tests |
| NFR-002 | Slice B — one shared formula | `test_expected_economics.py` attribution case |
| NFR-003 | Slice B — precompute only | `test_architecture_boundaries.py` addition |
| NFR-004 | Slice B — default off | `test_expected_economics.py` default-mode case |
| NFR-005 | Slices A-C | `test_expected_economics.py` LP-shape case |

## Trade-offs & Alternatives

- **Multiplying the coefficient vs. a separate expected-revenue term.** A separate term would let
  attribution show contractual and expected side by side in one solve, but it would double-count
  unless the contractual term were simultaneously zeroed — an error-prone construction. Scaling the
  single coefficient keeps one number per route and puts the comparison in the disclosure section
  instead.
- **Entity scope on the limit vs. a separate netting-set contract.** §22.9 speaks of "borrower
  netting sets," which argues for a first-class contract. Two optional fields on
  `CounterpartyLimit` is the smaller change and expresses both of §22.9's summations; a netting-set
  contract can supersede it later if agency/prime work (T36-T39) needs one. Recorded rather than
  silently preferred.
- **Fail-closed vs. warning for entity mappings.** §22.9 states fail-closed for hard aggregation;
  `0011` chose warnings for status/calendar. **Resolved (2026-09-15) by the distinguishing
  principle: warn when a check only annotates an answer the optimizer would have produced anyway;
  fail closed when the uncertain data determines the content of a constraint.** `0011`'s checks
  change no bound and no coefficient — drop them and you get the identical solve. An entity mapping
  changes the feasible region, and its failure mode is asymmetric: omission relaxes a credit limit
  (a control failure) while over-inclusion only costs revenue (a P&L miss).
- **Confidence threshold vs. approval as the gate.** Resolved in favor of approval, with confidence
  retained as a screening/reporting signal. A pure threshold would let a vendor's score set the
  firm's netting sets, which §22.1's source-of-truth table assigns to the internal credit/risk
  system; it also handles both error directions badly (a wrong 0.99 binds unseen; a correct 0.40 is
  unusable without weakening the global threshold for everyone). Cost, recorded honestly: nothing
  upstream populates `approval_reference` yet, so entity-scoped hard limits are unusable until an
  approval workflow exists — the same built-but-not-activatable posture as `0011`'s synthetic
  adapter and this spec's own G3 gating.

## Validation Strategy

1. Full existing suite (326 passed) green after every task, not only at the end.
2. Byte-identical checks for each slice's absent-default before any new behavior test is written —
   the NFR-001 gate, following `0011`'s own regression-first discipline for `0010`'s code.
3. Hand-computed expected-revenue arithmetic in the golden test (AC-011), so a formula drift fails
   rather than merely changing a plausible number.
4. An LP-shape assertion (AC-014) proving no integer/quadratic variable appears when all three
   slices are exercised together.
5. A `hypothesis` property test for `expected_active_fraction`'s clamp across the full input range.
6. An architecture-boundary addition asserting no module fits/trains anything (NFR-003) — in
   practice, that no estimation library is imported anywhere under `src/inventory_optimizer`.

## Rollout, Observability & Rollback

- Purely additive. Rollback is reverting the three slices independently; no migration, no config
  rewrite (a config predating `economics_mode` is valid and means `contractual`).
- The disclosure section is the operational surface a G3 review would read: mode, per-route model
  versions, calibration dates, uncertainty, and the shadow comparison.
- No new dependency: every computation here is arithmetic over existing contracts.

## Open Questions

None outstanding. All four were resolved by the owner on 2026-09-15 and are recorded in full in
`spec.md`'s Assumptions & Open Questions: shadow mode as the default, the PWL deferral, the
three-part refinement of the fail-closed entity rule (narrowed scope, approval as the authority, no
escape hatch), and the dual-R-numbering defect — that last one already corrected in
`TRACEABILITY.md` rather than left for T-013.
