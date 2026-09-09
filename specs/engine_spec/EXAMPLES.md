# Engine Spec Worked Examples and Golden Fixtures

## Purpose and Authority

This document translates the normative requirements in `01_SPEC.md` into small, deterministic cases
that an engineer, quant, desk user, and reviewer can calculate independently. These examples are
intended to become golden test fixtures under
`projects/inventory_optimizer/tests/golden/`.

`01_SPEC.md` remains authoritative. If an example conflicts with the specification, fix the example
and add a regression test; do not change implementation behavior to preserve an incorrect fixture.

The examples use continuous shares so the expected answers remain LP solutions. MIP variants are
called out explicitly. Unless stated otherwise:

- prices are USD per share;
- rates are annual decimals on ACT/360;
- the horizon is one day, so `tau = 1 / 360`;
- fee rates are lender-side rates;
- revenue share is `1.0`;
- reinvestment, variable, capital, transition, and soft-policy costs are zero;
- demand is a post-state cap rather than incremental demand;
- all records share the same valid `as_of` and effective date;
- all routes, owners, borrowers, clients, agreements, and collateral are eligible;
- no rounding is applied; and
- reported values may be rounded, but fixture assertions use configured tolerances.

---

## Example Index

| ID | Case | Primary behavior | Expected status |
| --- | --- | --- | --- |
| E1 | Scarce-name allocation | Higher net fee receives scarce inventory first | `OPTIMAL` |
| E2 | Fee elasticity shock | Higher fee reduces demand before LP construction | `OPTIMAL` |
| E3 | Proposed sale and recalls | Settled supply reduction changes post-state routes | `OPTIMAL` or `INFEASIBLE` variant |
| E4 | Eligibility schedule | Deny, grandfather, and recall-only compile into bounds | `OPTIMAL` or `INFEASIBLE` variant |
| E5 | Collateral capacity and joint allocation | Haircut-adjusted credit and concentration bind | `OPTIMAL` |
| E6 | Agency beneficial-owner allocation | Owner balances and mandates prevent commingling | `OPTIMAL` |
| E7 | Prime inventory sourcing | Internal and external sources cover a hard client demand | `OPTIMAL` or `INFEASIBLE` variant |
| E8 | Strict infeasibility and explicit repair | Non-relaxable rules remain hard; allowed service rule may repair | `INFEASIBLE` or repaired result |
| E9 | Platform invocation equivalence | Direct and QR Haven adapter calls have identical semantics | Same as underlying solve |

---

## E1 — Scarce-Name Allocation

### Question

How should 100 lendable shares be allocated when Route A pays more than Route B and utilization is
capped at 90%?

### Inputs

| Input | Value |
| --- | ---: |
| Total lendable `L` | 100 shares |
| Reserved `R` | 0 shares |
| Committed `C` | 0 shares |
| Price `P` | USD 10/share |
| Maximum utilization | 90% |
| Route A current quantity | 0 shares |
| Route A maximum/demand | 80 shares |
| Route A fee | 2.00% |
| Route B current quantity | 0 shares |
| Route B maximum/demand | 80 shares |
| Route B fee | 1.00% |

### Compiled model

```text
maximize (10 / 360) * (0.02 * q_A + 0.01 * q_B)

subject to
    q_A + q_B + a = 100
    q_A + q_B <= 90
    0 <= q_A <= 80
    0 <= q_B <= 80
    a >= 0
```

### Expected result

| Output | Expected value |
| --- | ---: |
| `q_A` | 80 shares |
| `q_B` | 10 shares |
| Post on-loan | 90 shares |
| `a` / available | 10 shares |
| Utilization | 90% |
| Route A one-day fee revenue | USD 0.0444444444 |
| Route B one-day fee revenue | USD 0.0027777778 |
| Total one-day fee revenue | USD 0.0472222222 |
| Inventory residual | 0 shares |

### Required assertions

- Status is `OPTIMAL` and the independent verifier passes.
- Route A fills before Route B because every non-fee term is equal.
- `HIGHER_NET_FEE`, `INVENTORY_SCARCE`, and `UTILIZATION_CAP_BINDING` are supported by structured
  evidence.
- Removing the utilization cap produces `q_A = 80`, `q_B = 20`, and `a = 0`.

---

## E2 — Fee Elasticity Shock

### Question

What happens to demand when a route's fee increases from 2.00% to 3.00% with constant elasticity
`epsilon = 0.5`?

### Inputs and preprocessing

```text
Q_ref = 80
F_ref = 0.02
f_scenario = 0.03
epsilon = 0.5

D(f) = Q_ref * (f / F_ref) ** (-epsilon)
     = 80 * (0.03 / 0.02) ** (-0.5)
     = 65.3197264742
```

Supply is 100 shares, price is USD 10, and no other cap binds.

### Expected result

| Output | Baseline | Fee-shock scenario |
| --- | ---: | ---: |
| Fee | 2.00% | 3.00% |
| Effective demand cap | 80.0000000000 | 65.3197264742 |
| Post allocation | 80.0000000000 | 65.3197264742 |
| Available | 20.0000000000 | 34.6802735258 |
| One-day fee revenue | USD 0.0444444444 | USD 0.0544331054 |

The scenario earns more despite lower quantity because elasticity is below one. That observation is
specific to these inputs; the optimizer reports the result rather than assuming a fee increase is
always beneficial.

### Required assertions

- Elasticity is evaluated before model construction in baseline LP mode.
- The scenario contains `ELASTICITY_REDUCED_DEMAND`.
- The baseline request/hash is unchanged after the scenario.
- Batch and isolated scenario results agree within tolerance.

---

## E3 — Proposed Sale and Recall Feasibility

### Baseline

Use E1 with the utilization cap removed and treat the result as the current book:

```text
L = 100
q0_A = 80
q0_B = 20
a0 = 0
```

A sale of 30 shares settles on the scenario effective date, so post-sale lendable supply is 70.

### Feasible open-loan variant

Both routes are open and immediately reducible. Transition costs are zero.

```text
q_A + q_B + a = 70
0 <= q_A <= 80
0 <= q_B <= 80
```

Expected result:

| Output | Value |
| --- | ---: |
| Route A post quantity | 70 shares |
| Route B post quantity | 0 shares |
| Route A decrease | 10 shares |
| Route B decrease | 20 shares |
| Total required decrease/recall | 30 shares |
| Available | 0 shares |

The optimizer retains the higher-fee route because transition terms are equal. The result includes
`TRADE_REDUCED_SUPPLY`, lost route economics, and the exact routes affected.

### Infeasible term/notice variant

If Route A has a hard post-state minimum of 80 through the sale settlement date, Route B can fall to
zero but at least 80 shares must remain on loan against only 70 lendable shares.

Expected behavior:

- strict status is `INFEASIBLE`;
- no allocation recommendation is returned;
- diagnostics identify the sale-adjusted inventory equality and Route A term/recall lower bound;
- inventory conservation and the contractual lower bound are not repairable; and
- the report states that at least 10 additional timely shares or an approved contractual change is
  required.

---

## E4 — Eligibility Schedule Actions

### Baseline state

| Item | Value |
| --- | ---: |
| Lendable supply | 100 shares |
| Existing Route G | 40 shares |
| New candidate Route N | maximum 50 shares |
| Available before new allocation | 60 shares |

An approved, bitemporal schedule is observed before `as_of` and effective for the solve.

### Rule set

| Rule | Route | Action | Expected compiled effect |
| --- | --- | --- | --- |
| `RULE-G` | Existing G | `GRANDFATHER` | `0 <= q_G <= 40` unless contract floor is higher |
| `RULE-N` | Candidate N | `DENY` | `q_N = 0` |

### Expected result

With positive economics and no other route, `q_G = 40`, `q_N = 0`, and `a = 60`. The result retains
schedule ID, version, both rule IDs, authority, approval, observed time, effective interval, and
bound lineage. It contains `ELIGIBILITY_SCHEDULE_BOUND`.

### Recall-only variant

Replace `RULE-G` with `RECALL_ONLY` and an approved ceiling of 25 shares by the effective date.

- If the route is contractually reducible, expected `q_G = 25` and `a = 75`.
- If a term/notice lower bound requires `q_G >= 40`, the strict model is infeasible.
- Schedule precedence cannot silently override the contractual lower bound.
- An unapproved scenario overlay cannot replace the restrictive rule with `ALLOW`.

---

## E5 — Collateral Capacity and Joint Allocation

### E5A — Capacity mode

One borrower route has price USD 20/share, demand 100 shares, margin factor `1.02`, and approved
collateral-credit capacity `K_coll = USD 1,530`.

```text
1.02 * 20 * q <= 1,530
q <= 75
```

Expected allocation is 75 shares, assuming supply is at least 75. The result contains
`COLLATERAL_CAPACITY_BINDING` and reports USD 1,530 of required/used collateral credit.

### E5B — Joint mode with concentration

Available collateral market values:

| Collateral | Available market value | Haircut | Recognized credit per USD |
| --- | ---: | ---: | ---: |
| Cash `c1` | USD 1,000 | 0% | 1.00 |
| Government bonds `c2` | USD 600 | 5% | 0.95 |

The schedule limits government bonds to 30% of total assigned collateral market value:

```text
y_c2 <= 0.30 * (y_c1 + y_c2)
y_c1 <= 1,000
y_c2 <= 600

y_c1 + 0.95 * y_c2 >= 1.02 * 20 * q
```

At maximum coverage:

```text
y_c1 = 1,000
y_c2 = 428.5714285714
recognized_credit = 1,407.1428571429
q = 1,407.1428571429 / 20.4
  = 68.9775910364
```

### Required assertions

- Assigned collateral never exceeds either asset's availability.
- Haircuts reduce market value to recognized credit under the canonical convention.
- The bond concentration row binds and produces `COLLATERAL_CONCENTRATION_BINDING`.
- Coverage equals or exceeds required margin-adjusted loan exposure.
- Cash reinvestment income, if enabled, is computed from assigned cash once and not also from route
  notional.
- Whole lots or minimum transfer amounts are tested separately as MIP cases.

---

## E6 — Agency Beneficial-Owner Allocation

### Question

Can unused inventory from one owner be used to exceed another owner's supply or mandate?

### Inputs

| Input | Owner A | Owner B |
| --- | ---: | ---: |
| Total lendable | 60 | 40 |
| Reserved/committed | 0 | 0 |
| Current on-loan | 0 | 0 |
| Mandate maximum on-loan | 60 | 20 |
| Eligible common borrower demand | 100 total | 100 total |
| Route fee | 1.50% | 1.50% |

Fairness is disabled and all positive economics are otherwise equal.

### Model fragment

```text
q_A + a_A = 60
q_B + a_B = 40
q_A <= 60
q_B <= 20
q_A + q_B <= 100
```

### Expected result

| Output | Value |
| --- | ---: |
| Owner A allocation | 60 shares |
| Owner A available | 0 shares |
| Owner B allocation | 20 shares |
| Owner B available | 20 shares |
| Total allocation | 80 shares |
| Unfilled demand | 20 shares |

Owner B's remaining 20 shares cannot be relabeled as Owner A inventory, and the common borrower
demand does not override B's mandate. The result contains `OWNER_MANDATE_BOUND` and reconciles
quantity and revenue separately for both owners.

### Agency variants

- A contractual pro-rata requirement is a hard LP row.
- An approved fairness preference uses explicit deviation variables or a convex QP term and reports
  `AGENCY_FAIRNESS_TRADEOFF` when material.
- An exclusive borrower/program decision uses MIP when the optimizer selects the exclusive.
- An indemnification cost must appear as a separate objective attribution and reason code rather
  than a hidden reduction to the fee.
- An owner-withdrawal scenario uses the same timing and recall-feasibility logic as E3.

---

## E7 — Prime Inventory Sourcing

### Question

How should a hard 100-share client short be covered from a cheaper internal source and a more
expensive external borrow?

### Inputs

| Input | Internal source `s1` | External source `s2` |
| --- | ---: | ---: |
| Authorized capacity | 60 shares | 50 shares |
| Fully adjusted annual source cost | 0.20% | 0.80% |
| Price | USD 50/share | USD 50/share |
| Settlement timing | Same day | Same day |

Client fee is 1.00%; client demand `d1` is a settled hard obligation of 100 shares. There are no
other costs or constraints.

### Compiled model

```text
maximize (50 / 360) * [0.01 * (x_s1d1 + x_s2d1)
                        - 0.002 * x_s1d1
                        - 0.008 * x_s2d1]

subject to
    x_s1d1 <= 60
    x_s2d1 <= 50
    x_s1d1 + x_s2d1 = 100
    x_s1d1, x_s2d1 >= 0
```

### Expected result

| Output | Value |
| --- | ---: |
| Internal allocation | 60 shares |
| External allocation | 40 shares |
| Unfilled hard demand | 0 shares |
| One-day client gross revenue | USD 0.1388888889 |
| One-day internal source cost | USD 0.0166666667 |
| One-day external source cost | USD 0.0444444444 |
| One-day net before other costs | USD 0.0777777778 |

The cheaper authorized source fills first. The result reports internalization of 60%, the external
lender/quote/agreement lineage, `EXTERNAL_BORROW_SELECTED`, and full source/client reconciliation.

### Prime variants

- If the external quote expires before the decision cutoff, only 60 shares remain and the hard
  settled obligation is `INFEASIBLE`.
- If `d1` is an indicative locate rather than a settled obligation, a feasible result may allocate
  60 and report `unfilled = 40` with its explicit service treatment.
- Client-reuse inventory is absent unless effective consent and agreement authority resolve. A
  rejected source produces `CLIENT_REUSE_NOT_AUTHORIZED`.
- A binding funding/capital budget produces `BALANCE_SHEET_LIMIT_BINDING`.
- All-or-none quotes, fixed source activation fees, and source-count limits require MIP.

---

## E8 — Strict Infeasibility and Explicit Repair

### E8A — Non-relaxable conflict

```text
post lendable supply = 50
existing term-loan hard minimum = 60
available >= 0
```

No solution can satisfy both inventory conservation and the contractual minimum. Expected behavior:

- status `INFEASIBLE`;
- no allocation recommendation;
- inventory and legal term rows identified in diagnostics; and
- repair mode refuses to soften either row.

### E8B — Allow-listed service repair

```text
post lendable supply = 70
demand = 100
approved service floor = 80
service floor is allow-listed for explicit repair
```

The strict model is infeasible. If the caller explicitly enables repair, the second solve returns:

```text
q = 70
service_floor_slack = 10
available = 0
```

The result remains labeled `repaired`; it is not represented as the strict optimum. It reports the
10-share relaxation, penalty, priority, approval policy, and strict infeasibility. Inventory
conservation remains exact.

---

## E9 — Existing-Platform Invocation Equivalence

### Direct call

```python
config = load_config(
    environment="test",
    desk="inventory_core",
    formulation="lp",
    objective="net_revenue",
    policy="standard",
)

result_direct = InventoryOptimizer(config=config).optimize(request)
```

### QR Haven platform call

```python
context = PlatformInvocationContext(
    correlation_id="corr-e9",
    idempotency_key="idem-e9",
    authorization_reference="authz-e9",
    request_schema_version="1",
    problem_family="securities_lending_inventory",
)

result_platform = qr_haven_inventory_optimizer.optimize(
    platform_request,
    invocation_context=context,
)
```

The platform adapter must normalize `platform_request` to the exact canonical `request` used by the
direct call.

### Required assertions

- Canonical request, config, component-manifest, compiled-problem, and result hashes agree.
- Status, allocations, objective attribution, explanations, and verification metrics agree.
- The platform result additionally retains correlation, idempotency, authorization, and schema
  references without embedding user-session or ORM objects.
- Reusing `idem-e9` with the same request/config returns or references the same completed result.
- Reusing `idem-e9` with a different canonical request/config hash is rejected.
- Moving execution from in-process to a worker or service transport cannot change mathematical
  semantics.
- The adapter cannot persist or display an unverified allocation as a recommendation.

---

## Fixture Layout

Recommended implementation layout:

```text
tests/golden/
├── core/
│   ├── e1_scarce_name/
│   ├── e2_elasticity/
│   ├── e3_proposed_sale/
│   ├── e4_eligibility/
│   ├── e5_collateral/
│   └── e8_infeasibility/
├── agency/
│   └── e6_owner_allocation/
├── prime/
│   └── e7_source_selection/
└── platform/
    └── e9_invocation_equivalence/
```

Each directory should eventually contain:

- canonical input JSON;
- resolved configuration YAML and hash;
- synthetic schedule/reference fixtures;
- expected normalized result JSON;
- expected compiled variable/row names and selected coefficients;
- tolerance metadata;
- explanation/reason-code assertions; and
- a README describing the economic expectation.

Fixtures must be synthetic, pseudonymous, deterministic, small enough for hand calculation, and
free of licensed Bloomberg payloads or proprietary field names.

---

## Golden-Update Policy

A golden result is updated only when:

1. a reviewed specification or decision record changes intended behavior;
2. the mathematical difference is explained and independently calculated;
3. objective, balance, constraint, and reason-code deltas are reviewed;
4. baseline-family behavior is checked when desk extensions change;
5. platform/direct equivalence still passes; and
6. the change updates `TRACEABILITY.md`, affected tests, model notes, and approvals together.

A solver-version change alone is not sufficient reason to accept a different allocation. Equivalent
degenerate optima require deterministic tie-breaking or set-valued acceptance explicitly documented
in the fixture.
