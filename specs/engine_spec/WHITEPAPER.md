# A Point-in-Time, Economics-Aware Inventory Optimizer for Securities Lending

## Design Whitepaper

**Project:** `inventory_optimizer`

**Status:** Proposed architecture and mathematical design

**Primary formulation:** Sparse linear programming

**Primary solver:** HiGHS through a solver-neutral adapter

**Extension path:** MIP, convex QP, robust/stochastic LP, multi-period optimization, and optional NLP

**Implementation evidence:** `EXAMPLES.md` defines deterministic golden cases and
`TRACEABILITY.md` maps requirements to planned modules, tests, tasks, releases, and gates.

---

## Abstract

Securities-lending inventory allocation is often described as a simple ranking problem: lend scarce
shares to the borrower paying the highest fee. That framing is incomplete. A usable decision must
reconcile shares already on loan with available and reserved inventory, respect beneficial-owner and
counterparty rules, distinguish quoted from realized demand, account for the cost and timing of
recalls, and anticipate how trades, corporate actions, liquidity, and fee changes alter the state.

This whitepaper proposes a modular optimization engine, initially integrated into the existing QR
Haven platform, whose first production model is a sparse linear program. The optimizer has its own
package, configuration, domain, services, tests, and result contract, while the host platform owns
identity, authorization, upstream connectivity, persistence, and presentation. The primary decision
is the post-optimization quantity on each eligible route from an inventory pool and security to a
borrower. Fee rates are exogenous in the baseline model, while a point-in-time elasticity model
converts fee assumptions into demand caps. Exact inventory equalities prevent shares from being
created or lost. Linear economic terms capture fee income, collateral reinvestment, variable costs,
and allocation-transition costs. Explicit policies constrain utilization, reserves, demand,
counterparties, and concentration.

The design separates the inventory-specific domain from reusable optimization infrastructure. It
uses immutable scenario overlays for proposed trades and market shocks, independent post-solve
verification, versioned component registries, and normalized solver statuses. Bloomberg-derived
reference, entity, corporate-action, holdings, event, pricing, status, and liquidity data can enrich
the model through bitemporal adapters, while internal books, contracts, eligibility, and limits
remain authoritative.

The result is not only an allocation vector. It is a verified recommendation with balance
reconciliation, objective attribution, binding constraints, local sensitivity, uncertainty, and a
complete audit envelope. The architecture supports opt-in agency-lending and prime-inventory-
financing problem families plus later discrete, quadratic, robust, multi-period, and nonlinear
extensions without obscuring the first model's economics or operational meaning.

---

## 1. Problem Setting

### 1.1 Securities lending is a search-and-allocation market

A security lender controls finite, fragmented inventory across beneficial owners, accounts, legal
entities, and settlement locations. Borrowers request quantities under negotiated terms. The lender
must determine whether inventory is eligible, whether existing loans should remain or be recalled,
and which competing demand should receive scarce capacity.

The economics are not described by a centralized exchange price alone. Research on equity lending
emphasizes the roles of shortability, lending fees, recalls, search, bargaining, fee dispersion, and
scarcity. D'Avolio documents loan supply, fees, and recalls in the stock-borrow market [1]. Duffie,
Gârleanu, and Pedersen model search and bargaining over lending fees [2]. Kolasinski, Reed, and
Ringgenberg find that fee responses and dispersion become especially relevant when demand and search
frictions are high [3]. These observations motivate borrower- and route-aware allocation rather than
a security-level fee sort.

### 1.2 Why a greedy allocator is insufficient

A greedy rule can rank candidate requests by fee or fee times quantity. It generally cannot jointly
answer:

- whether the inventory balance is correct after reserves and pending settlements;
- whether a higher-fee loan is worth recalling an existing relationship;
- whether a sell requires a recall that can complete before settlement;
- whether borrower demand falls when the proposed fee rises;
- whether entity-level, beneficial-owner, or concentration limits bind;
- whether expected loan take-up/survival supports the contractual run-rate revenue;
- whether corporate actions or market liquidity make an apparently attractive allocation fragile;
- whether a partial fill, minimum ticket, or one-price rule is operationally valid; or
- what the marginal value of an additional lendable share is.

A mathematical program makes these tradeoffs simultaneous, explicit, and testable.

### 1.3 Design objective

The system should maximize risk- and cost-adjusted lending economics subject to exact inventory and
approved policy. It should preserve a simple baseline that a desk, engineer, auditor, and model-risk
reviewer can reconstruct independently.

The engine is decision support. It is not a position book, contract system, market-data terminal,
execution system, or unreviewed automated trader.

---

## 2. Contributions of the Proposed Design

The design contributes ten connected ideas:

1. **Post-state route allocation.** Optimize the desired quantity on each existing or candidate
   route, so retention, recall, and new allocation use one variable system.
2. **Exact inventory conservation.** Represent available-to-lend as a balance variable in an
   equality, not as an after-the-fact calculation.
3. **Economics in consistent units.** Convert annual rates, prices, expected activity, and one-time
   transition costs into USD over one declared horizon.
4. **Elasticity without premature nonlinearity.** Evaluate demand at exogenous fee assumptions
   before LP construction, while reserving MIP/NLP paths for joint pricing.
5. **Immutable what-if analysis.** Express trades, events, rates, demand, and policy changes as
   typed overlays on a common baseline.
6. **Point-in-time enrichment.** Separate when a value applies from when it became known and retain
   source/mapping lineage.
7. **Solver-neutral verification.** Compile a sparse mathematical contract, isolate HiGHS, and
   verify the returned solution outside the solver.
8. **Progressive realism.** Add discrete rules, expected activity, liquidity, uncertainty,
   multi-period balances, and transformations only when their incremental value is measurable.
9. **Platform-integrated modularity.** Use a one-way host adapter and canonical invocation/result
   contracts so the optimizer operates inside QR Haven but remains independently testable and
   extractable.
10. **Desk-specific problem families.** Reuse the verified kernel for agency owner allocation and
    prime inventory sourcing without hiding different economics behind one route flag.

---

## 3. Canonical Inventory State

### 3.1 Balance definitions

For inventory record `i`, representing one pool/security:

```text
L_i = gross_inventory_i - ineligible_inventory_i - policy_exclusions_i
```

`L_i`, total lendable, includes shares already on loan. Current available-to-lend is:

```text
available_i = L_i - on_loan_i - reserved_i - committed_out_i
```

This definition matters because upstream feeds use “lendable supply” inconsistently. An adapter must
state whether a source quantity includes existing loans and reserves. The optimizer must reject an
ambiguous convention rather than repair it heuristically.

### 3.2 Inventory fragmentation

Two positions in the same security are not automatically interchangeable. A pool can differ by:

- beneficial owner and contractual revenue share;
- legal eligibility and voting policy;
- tax and manufactured-payment treatment;
- collateral and indemnification economics;
- custody or settlement location;
- currency and market;
- counterparty access;
- recall notice and event restrictions; and
- internal reserve policy.

Therefore the base inventory key is `(inventory_pool_id, security_id)`, not security alone.

### 3.3 Point-in-time identity

Security and entity mappings change. A point-in-time record contains an economic effective interval
and an observation time. Historical data is not rewritten after ticker, share-class, issuer, parent,
or corporate-action changes.

This gives a historical solve the information set that actually existed at the decision time, which
is a prerequisite for credible backtesting.

---

## 4. Decisions, Routes, and Demand

### 4.1 Route representation

A route `j` connects:

```text
inventory pool/security -> borrower -> demand group -> economic and contractual terms
```

It contains a current quantity `q0_j`, a feasible post-state interval `[lb_j, ub_j]`, fee and cost
terms, recall/term restrictions, and identifiers for policy aggregation.

One post-state variable `q_j` covers both existing and candidate routes:

- `q_j = q0_j`: retain the route;
- `q_j > q0_j`: increase or originate;
- `q_j < q0_j`: return, reduce, or recall;
- `q_j = 0`: close or do not activate.

Change variables make transition costs linear:

```text
q_j - q0_j = inc_j - dec_j
0 <= inc_j <= max(ub_j - q0_j, 0)
0 <= dec_j <= max(q0_j - lb_j, 0)
```

### 4.2 Demand groups

A demand group contains routes competing to serve the same borrower/security need. Its cap must have
one explicit semantic:

- total post-state borrower capacity; or
- incremental demand separated from retained existing demand.

Mixing these interpretations double-counts or unintentionally recalls existing loans.

### 4.3 Elasticity

The default constant-elasticity curve is:

```text
D_raw_g(f_g)
  = Q_ref_g * (max(f_g, fee_floor) / F_ref_g) ** (-epsilon_g)
```

where `epsilon_g >= 0`. Effective demand incorporates uncertainty and hard limits:

```text
D_g = clip(
    D_raw_g(f_g) - uncertainty_haircut_sigma * forecast_std_g,
    0,
    hard_max_g,
)
```

Fee is fixed for the LP solve, so `D_g` is a parameter. This captures first-order price response
without multiplying two decision variables.

### 4.4 Demand realism

Requested, approved, and realized quantities differ. Approved and realized loan data are censored by
inventory and policy. Fees are endogenous because scarcity also affects negotiated rates. A mature
demand process should use requested and rejected locates, cancellations, take-up, survival, returns,
events, market state, ownership, and utilization. It should estimate borrower/security elasticity
with hierarchical peer shrinkage and report uncertainty.

The optimizer consumes those estimates; it does not train them inside the solve path.

---

## 5. Baseline Linear Program

### 5.1 Sets and parameters

- `I`: inventory records.
- `J`: loan routes.
- `G`: demand groups.
- `B`: borrowers or approved entity aggregates.
- `J(i)`, `J(g)`, `J(b)`: routes belonging to each group.
- `L_i`, `R_i`, `C_i`, `P_i`: lendable, reserved, committed, and price.
- `q0_j`, `lb_j`, `ub_j`: current quantity and post-state bounds.
- `f_j`, `s_j`, `r_j`, `h_j`, `c_j`: fee, revenue share, reinvestment, schedule-derived eligible
  cash-collateral/notional factor, and variable-cost rates. In joint collateral mode, `h_j` is zero
  and assigned cash collateral drives reinvestment economics.
- `k+_j`, `k-_j`: one-time increase and decrease cost per share.
- `D_g`: effective demand cap.
- `tau`: planning-horizon year fraction.

### 5.2 Decision variables

- `q_j`: post route quantity.
- `inc_j`, `dec_j`: positive and negative change.
- `a_i`: post available-to-lend.
- optional named deviation/slack variables for configured soft targets.

### 5.3 Inventory equality

For every inventory record:

```text
sum(q_j for j in J(i)) + a_i = L_i - R_i - C_i
```

This equality is the model's accounting spine. `a_i >= 0`; therefore a result cannot lend more than
usable inventory.

### 5.4 Demand and route capacity

```text
lb_j <= q_j <= ub_j

sum(q_j for j in J(g)) <= D_g
```

Bounds encode eligibility, existing term/recall restrictions, effective settlement, route capacity,
and approved grandfather policy.

### 5.5 Utilization and reserves

Let `O_i = sum(q_j for j in J(i))`. Optional hard limits are:

```text
u_min_i * L_i <= O_i <= u_max_i * L_i
a_i >= required_buffer_i
```

A preferred target can use positive/negative deviation variables. Its penalty is zero by default so
the engine does not create uneconomic loans merely to improve a KPI.

### 5.6 Counterparty and concentration limits

For an approved borrower/entity aggregate `b`:

```text
sum(P_i(j) * q_j for j in J(b)) <= counterparty_limit_b
```

Similar precompiled groups support security, issuer, parent, pool, country, or collateral-type
limits. Bloomberg entity relationships can enrich the hierarchy; internal credit/legal mappings
determine the enforceable aggregation.

### 5.7 Eligibility schedules

Eligibility is time-, owner-, borrower-, agreement-, security-, market-, event-, and collateral-
dependent. A versioned schedule resolves each route to `ALLOW`, `DENY`, `GRANDFATHER`,
`RECALL_ONLY`, or `REVIEW`, plus quantitative limits such as maximum lend fraction, reserve,
minimum fee, maximum term, and permitted collateral schedules.

Resolved rules compile into bounds and group rows. A newly denied candidate receives no capacity.
An existing route may be grandfathered or placed on a feasible recall path; a policy change does not
make a term loan instantly recallable. Denials and non-relaxable rules take safety precedence, while
quantitative hard limits normally intersect. Unresolved conflicts fail closed.

Each bound/row retains the schedule, rule, version, authority, approval, observation time, and
effective interval that produced it.

### 5.8 Collateral schedules

Collateral matters when it changes route eligibility, economic value, credit exposure, capacity, or
operational feasibility. A schedule defines eligible collateral, valuation, margin, haircuts,
currency treatment, concentration, wrong-way exclusions, availability, substitution, settlement,
reuse/segregation, and cash-reinvestment terms.

The design supports three modes:

- **Validate only:** external collateral allocation is checked against the applicable schedule.
- **Capacity:** haircut-adjusted collateral capacity limits loan exposure.
- **Joint:** the optimizer allocates collateral and loan inventory together.

In joint mode, let `y_jc` be collateral market value assigned from collateral asset/type `c` to route
`j`, `H_jc` the canonical haircut, and `A_c` available collateral market value:

```text
sum_c (1 - H_jc) * y_jc
    >= margin_factor_j * P_i(j) * q_j

sum_j y_jc <= A_c
```

Only schedule-eligible `(j,c)` pairs exist. Linear rows can also enforce issuer, country, currency,
asset-type, and borrower concentration. Minimum transfers, whole lots, discrete substitutions, and
exclusive collateral choices require MIP; substitution timing and margin calls belong in the
multi-period model.

The haircut convention above reduces market value to recognized credit. An alternative source
convention must be converted and preserved in lineage. No percentage is treated as universally
correct. Basel Committee guidance similarly emphasizes defined eligible-collateral policies,
risk-sensitive haircuts, margin sufficiency, delivery delay, and substitution risk in securities-
financing transactions [13, 14]; actual applicability remains agreement-, firm-, and
jurisdiction-specific.

### 5.9 Objective

The default objective maximizes net USD economics over the horizon:

```text
maximize
    sum_j P_i(j) * q_j * tau
          * (f_j * s_j + r_j * h_j - c_j)
  - sum_j (k+_j * inc_j + k-_j * dec_j)
  - explicit_utilization_penalties
  - explicit_service_penalties
  - other_registered_linear_penalties
```

That route-level reinvestment term applies to validate/capacity modes. Joint collateral mode
replaces it with objective terms over assigned cash collateral `y_jc`; the component manifest
permits exactly one method so collateral income is not counted twice.

The solver may receive an equivalent scaled minimization vector. Reporting reconstructs the
unscaled maximization value from verified allocations.

### 5.10 Economic interpretation

The optimum reallocates inventory only if incremental horizon economics exceed transition and policy
costs. It can rationally retain a lower-fee current route when recalling and re-originating is too
expensive. When supply is scarce, an LP dual on the inventory equality estimates the local marginal
value of one more usable share.

---

## 6. From Contractual to Expected Economics

### 6.1 Expected active fraction

An approved quantity may never become a loan, and an active loan may return before horizon end. A
pre-solve model can estimate:

```text
expected_active_fraction_j
  = take_up_probability_j
    * conditional_expected_active_days_j / planning_horizon_days
```

The revenue coefficient becomes:

```text
expected_revenue_j
  = P_i(j) * q_j * tau
    * expected_active_fraction_j
    * (f_j * s_j + r_j * h_j)
```

Additional linear expected costs may cover repricing, manufactured payments, indemnification
capital, settlement failure, and event/relationship effects.

### 6.2 Separate outputs

The engine should report:

- contractual run-rate economics;
- expected active-horizon economics;
- transition and event costs;
- downside scenario economics; and
- realized outcomes when later available.

This separation prevents forecast adjustments from being mistaken for booked P&L.

### 6.3 Dynamic reserves

A flat reserve can be replaced with a precomputed, explainable buffer:

```text
required_buffer_i = max(
    legal_minimum_i,
    pending_settlement_need_i,
    demand_uncertainty_quantile_i,
    event_recall_buffer_i,
    liquidity_horizon_buffer_i,
)
```

Because this is a parameter, the model remains linear. Convex size-dependent recall/unwind costs can
be represented by piecewise-linear segments.

---

## 7. What-If Scenarios

### 7.1 Immutable overlays

A scenario overlays a baseline without modifying it. Supported events include BUY, SELL,
TRANSFER_IN, TRANSFER_OUT, NEW_LOAN, RETURN, and RECALL, plus rate, demand, inventory, and policy
shocks. Schedule overlays can activate/expire a known eligibility or collateral schedule version,
while collateral stresses can change valuation, FX, haircut add-ons, capacity, concentration, or
substitution/settlement assumptions. A permissive unapproved rule cannot be created by scenario.

The scenario compiler:

1. validates event identity, direction, quantity, and timing;
2. applies only changes effective by the solve date;
3. uses market/settlement calendars;
4. changes inventory and route state;
5. recalculates elasticity-adjusted demand;
6. validates and solves the complete post-state problem; and
7. compares it with the same verified baseline.

### 7.2 Proposed sales

A settled sale reduces `L_i`. If current loans plus reserves exceed the new usable inventory, the
optimizer must identify feasible recalls. If term or notice constraints prevent sufficient return by
settlement, the scenario is infeasible. It must not assume the book can sell loaned shares without an
operational consequence.

### 7.3 Scenario output

Each comparison includes:

- objective and expected-revenue delta;
- lendable, on-loan, available, and utilization delta;
- allocation increases/decreases and required recalls;
- elasticity-driven demand changes;
- constraint/slack changes;
- status, gap, runtime, and verification;
- structured reason codes; and
- config/input/scenario/data-version hashes.

Trade-price investment P&L stays separate from lending economics.

---

## 8. Bloomberg-Enriched Point-in-Time Layer

### 8.1 Useful data categories

Bloomberg describes reference-data coverage spanning instrument terms, legal entities, corporate
actions, classifications, holdings/ownership, and pricing [8]. Its event products describe company
and corporate-action calendars [9], its real-time data documentation includes identifiers, market
depth, security status, and end-of-day prices [10], and its funds data includes holdings and fund
corporate actions [11]. Bloomberg Liquidity Assessment provides size-, cost-, horizon-, and
scenario-oriented liquidity analytics across asset classes [12].

These categories can improve:

- security mastering and effective-dated identity;
- market and settlement calendars;
- corporate-action quantity/cash-flow/recall treatment;
- issuer and counterparty hierarchy candidates;
- sector/country/peer concentration;
- price, FX, volatility, spread, volume, status, and liquidity state;
- ownership/free-float and ETF/passive-flow features;
- dynamic reserves and unwind scenarios; and
- cold-start demand, take-up, return, and fee-regime models.

Exact fields and delivery mechanisms depend on licensed entitlements. Domain code names business
concepts; a versioned adapter maps available vendor fields into them.

### 8.2 Authority and reconciliation

Bloomberg data must not override:

- firm inventory and on-loan books;
- contractual loan terms;
- beneficial-owner eligibility;
- legal counterparty approval and limits;
- actual locate/loan activity; or
- internally approved netting/fungibility.

Conflicts produce a reconciliation issue or explicit approved override. Low-confidence entity or
security mappings fail closed for hard constraints.

### 8.3 Bitemporal correctness

Every enriched value carries:

- `observed_at`;
- `effective_from` and optional `effective_to`;
- source/version and mapping version;
- quality/freshness; and
- supersession/correction lineage where relevant.

Backtests select the latest observation known at the historical as-of, not today's corrected view of
the past. Corporate-action amendments and cancellations invalidate dependent scenarios without
rewriting prior knowledge.

### 8.4 Corporate actions

Corporate events can:

- transform quantities through splits or conversions;
- alter identity through mergers, spinoffs, or share-class changes;
- create manufactured-payment/tax economics;
- require elections, tenders, rights, or voluntary instructions;
- create voting/record-date recall needs; or
- interrupt tradability.

Deterministic quantity/cost effects can remain LP parameters. Discrete elections may require MIP.
Uncertain outcomes belong in named scenarios.

### 8.5 Liquidity analytics

Market liquidity affects whether a recall or sell can be completed at an acceptable cost/horizon.
Vendor estimates may parameterize buffers, PWL costs, or stress scenarios. They are estimates, not
guaranteed execution. Calibration against internal realized recalls, fails, and trading outcomes is
required before production use.

---

## 9. Solver and Software Architecture

### 9.1 Why LP and HiGHS first

The baseline problem is naturally sparse and linear when fee, demand cap, expected activity, and
reserve inputs are evaluated before solve. HiGHS is designed for large-scale sparse LP, MIP, and QP
models and exposes a Python interface [4]. The project nonetheless treats solver capabilities as
version-gated and proves them against the locked dependency.

LP provides:

- transparent coefficients and constraints;
- reliable global optimality for the linear model;
- dual/reduced-cost sensitivity;
- fast scenario re-solves;
- a strong benchmark for later complexity; and
- straightforward independent verification.

### 9.2 Layered system

```text
existing platform UI/API/jobs
                 |
                 v
QR Haven-owned optimizer adapter + invocation context
                 |
                 v
validation -> enrichment -> scenario application
                 |
                 v
eligibility/collateral/constraint schedule resolution
                 |
                 v
registered objective/constraint components
                 |
                 v
sparse compiled problem + reversible indexes
                 |
                 v
HiGHS or optional solver adapter
                 |
                 v
independent verifier -> attribution -> explanation -> audit
```

The inventory domain never imports HiGHS, Bloomberg connectivity, QR Haven, a web framework, or
dataframe operations. QR Haven owns the adapter and may import the optimizer; that dependency never
reverses.

### 9.3 Component registry

Decorators register stateless problem families, objective terms, constraints, and solvers with
immutable metadata. The resolved manifest declares versions, required inputs, variables/rows, and
capabilities. Unknown or duplicate components fail before formulation.

This supports new optimization problems without converting inventory records into generic
dictionaries. Shared abstractions should be extracted only after a second problem proves them.

### 9.4 Solver result contract

The backend returns normalized status, primal vector, optional duals/reduced costs, scaled/unscaled
objective, best bound/gap, iterations/nodes, runtime, native status, version, and effective options.

Normalized statuses distinguish optimal, feasible-limit, infeasible, unbounded, invalid, numerical,
interrupted, and solver-error outcomes. A timed-out incumbent is not called optimal.

### 9.5 Existing-platform integration

QR Haven is the initial runtime and integration boundary rather than a capability the optimizer
rebuilds. It authenticates and authorizes users, assembles book/record and approved schedule data,
supplies entitlements, schedules work, persists outputs, and presents approval workflows. The
optimizer receives canonical frozen records, resolves policy, compiles and solves the model,
verifies the result, and returns a versioned result envelope.

The integration may start as an in-process call or platform worker and later become a service only
if scaling or independent-release needs justify it. Correlation, authorization, schema, and
idempotency references cross the boundary; platform ORM/dataframe/session objects do not. Identical
canonical requests and configuration must have identical mathematical meaning in every transport.

### 9.6 Agency and prime problem families

Agency lending allocates separately owned inventory under beneficial-owner mandates. For owner `o`
and inventory record `i`:

```text
sum(q_j for j in J(o,i)) + a_oi = L_oi - R_oi - C_oi
```

No cross-owner flow exists without explicit authority. Agency economics include the contractual fee
split, collateral/reinvestment terms, servicing and transition costs, and separately attributed
indemnification exposure/cost. Mandates control borrower panels, collateral, utilization, term,
voting, tax, corporate-action, exclusive, and reporting behavior. Contractual allocation rules are
hard; optional fairness preferences are explicit soft LP or convex QP terms. Guidance for custody
and agency securities lending similarly highlights customizable client guidelines, borrower
approval/limits, and indemnification risk that should be reflected in pricing [15].

Prime inventory financing maps permitted sources `s` to client coverage demands `d` through
`x_sd`:

```text
sum_d x_sd <= source_capacity_s

sum_s x_sd + unfilled_d = demand_quantity_d
```

Settled shorts and committed delivery obligations fix `unfilled_d` to zero; indicative locates may
remain explicitly unfilled. Sources distinguish firm inventory, affirmatively reusable client
assets, affiliates, and external borrows. The objective nets client revenue against external borrow,
internal scarcity/transfer, funding, collateral, capital, liquidity, encumbrance, recall, fail,
buy-in, and operating costs. Client reuse defaults to unavailable without effective consent and
agreement authority. BIS analysis of the prime-broker/hedge-fund nexus highlights the relevance of
securities financing, position opacity, and wrong-way risk to prime-broker risk management [16].

Agency and prime profiles share bitemporal schedules, sparse compilation, scenarios, solver
adapters, statuses, audit, and independent verification. Disabling them leaves the baseline family
unchanged.

---

## 10. Discrete, Quadratic, and Nonlinear Extensions

### 10.1 Linear MIP

Binary/integer variables are justified by:

- all-or-none requests;
- minimum active tickets;
- integer or board-lot quantities;
- route activation costs;
- route-count limits and mutual exclusion; or
- one selected fee tier.

For route activation:

```text
q_j <= ub_j * z_j
q_j >= minimum_active_j * z_j
z_j in {0,1}
```

The big-M value is `ub_j`, derived from supply, demand, and policy.

### 10.2 Discrete pricing

Precompute demand `D_gk` at candidate fee tier `f_gk`:

```text
sum_k z_gk <= 1
0 <= q_gk <= D_gk * z_gk
```

Revenue `f_gk * q_gk` is linear because the fee at each tier is constant. This provides a controlled
step between exogenous LP fees and continuous nonlinear pricing.

### 10.3 Convex QP

Convex quadratic terms can penalize:

- concentration;
- correlated revenue/recall risk;
- squared allocation change; or
- smooth target deviations.

The matrix must be symmetric positive semidefinite, scaled, and attributable. Mixed-integer
quadratic capability is not inferred from continuous QP support.

### 10.4 Continuous nonlinear pricing

When fee `f_g` and demand `q_g = D_g(f_g)` are both decisions, revenue is nonlinear. A future model
may use PWL MIP, SCA, or an optional NLP solver. It must disclose local/global status, initialization,
convergence, and approximation error and retain a feasible LP fallback.

---

## 11. Robust and Multi-Period Extensions

### 11.1 Robust optimization

Demand, supply withdrawals, fees, returns, liquidity, and event outcomes are uncertain. Budgeted
robust optimization can protect selected coefficients/bounds while controlling conservatism.
Bertsimas and Sim formalize the tradeoff between nominal performance and protection—the price of
robustness—and show tractable robust counterparts for broad linear settings [6].

The inventory system should report:

- deterministic and robust objective;
- opportunity cost of robustness;
- protected uncertainty set/budget;
- downside improvement in named and out-of-sample scenarios; and
- constraints whose protection drives the change.

### 11.2 CVaR

CVaR can penalize the tail of revenue shortfall, forced recall cost, or settlement-failure loss.
Rockafellar and Uryasev provide an optimization representation that is especially useful with sampled
scenario losses [5]. A finite-scenario linear loss model can often remain an LP after auxiliary
variables are added.

Scenario probabilities and tails require calibration and versioning. A small arbitrary shock set is
stress testing, not evidence of statistical robustness.

### 11.3 Multi-period balances

For time bucket `t`:

```text
on_loan_i,t
  = on_loan_i,t-1 + new_loans_i,t - returns_i,t - recalls_i,t

lendable_i,t
  = lendable_i,t-1 + settled_buys_i,t - settled_sells_i,t
    + transfers_i,t + corporate_action_delta_i,t

available_i,t
  = lendable_i,t - on_loan_i,t - reserved_i,t - committed_i,t
```

This captures settlement and recall timing before introducing stochastic control. Deterministic
flows remain a sparse LP; discrete elections/lots make it MIP.

### 11.4 Transformation network

Approved ADR/share-class/cross-list/ETF conversions can form a network flow with ratios, capacities,
fees, FX, tax, and lags. Reference relationships identify candidates but do not establish fungibility.
Each edge requires legal and operational approval.

---

## 12. Verification, Explainability, and Governance

### 12.1 Independent verification

After every solve, independent code recalculates:

- variable bounds;
- row lower/upper violations;
- exact inventory balances;
- demand/utilization/counterparty constraints;
- schedule-derived eligibility bounds and effective rule lineage;
- collateral coverage, capacity, concentration, and assignment conservation when applicable;
- agency owner-level conservation and prime inventory-source/client-demand conservation when
  applicable;
- integrality and logical rules;
- scaled and unscaled objective values; and
- component attribution.

An unverified primal vector is never returned as a recommendation.

### 12.2 Infeasibility and repair

The strict model runs first. Diagnostics identify inconsistent balances, term/settlement conflicts,
and named constraint groups. Repair is a separate, explicitly enabled solve that may soften only
allow-listed internal targets. Inventory conservation, nonnegative availability, legal eligibility,
effective settlement, and hard legal/counterparty limits are never relaxed.

### 12.3 Explainability

Material changes receive structured reason codes such as:

- higher net fee;
- transition cost exceeds uplift;
- demand, reserve, utilization, or entity limit binding;
- trade reduced supply;
- elasticity reduced demand;
- event/liquidity buffer;
- term/recall restriction;
- eligibility/collateral schedule restriction;
- agency mandate, prime source, or balance-sheet restriction; or
- expected-activity adjustment.

The explanation derives from coefficients, slacks, bounds, duals, and deltas. Generated prose may
render it but does not establish correctness.

### 12.4 Model governance

Each release records:

- request/config/input/scenario/component hashes plus platform correlation/idempotency references;
- problem family, desk profile, schema version, and platform authorization reference;
- resolved schedule/rule, approval, and collateral-valuation hashes;
- data and model versions;
- solver version/options/status;
- formulation dimensions and stage timings;
- validation and verification metrics;
- fallbacks, approximations, warnings, and relaxations; and
- result hash and approval state.

Production promotion requires business, engineering, operations, risk/control, and model-risk review
appropriate to the capability.

---

## 13. Evaluation Framework

### 13.1 Correctness before economics

First prove:

- zero material inventory/bound/integrality violations;
- objective reconstruction;
- point-in-time and scenario isolation;
- stable status mapping;
- sparse scale behavior;
- deterministic golden outcomes;
- transport-equivalent canonical results;
- agency owner and prime source/client conservation when those families are enabled; and
- deterministic bitemporal schedule resolution and independently verified collateral constraints.

### 13.2 Shadow and walk-forward evaluation

Run recommendations beside the current process without execution. Compare:

- contractual and realized lending revenue;
- fee uplift net of recalls/setup/event/liquidity cost;
- utilization and availability buffers;
- filled/unfilled demand by value and priority;
- allocation churn and recall outcomes;
- settlement failures and corporate-action exceptions;
- downside scenario metrics;
- recommendation acceptance and override reasons;
- current process, greedy challenger, LP, and advanced model;
- agency owner opportunity-cost distribution and indemnification-adjusted return; and
- prime internalization, replacement cost, matched-book margin, and balance-sheet return.

### 13.3 Counterfactual caution

Historical “what would the optimizer have earned?” estimates face:

- censored demand;
- endogenous fees;
- unknown rejected opportunities;
- selection effects in realized loans;
- revised data and corporate-action histories;
- uncertain execution/take-up; and
- desk behavior changed by the recommendation itself.

Claims should separate exact accounting from forecasted counterfactual economics and use conservative
sensitivity ranges.

### 13.4 Promotion standard

An advanced model is promoted only if it improves a predeclared out-of-sample metric while preserving
correctness, operational feasibility, stability, latency, and explanation coverage. Complexity alone
is not progress.

---

## 14. Limitations

The proposed baseline does not:

- train demand or hazard models inside optimization;
- guarantee that a locate becomes a loan;
- guarantee vendor liquidity cost or return timing;
- model multi-currency collateral/reinvestment portfolios;
- jointly allocate collateral unless the explicit joint mode is enabled;
- apply agency or prime semantics unless the corresponding problem family is enabled and supplied
  with approved desk records;
- solve continuous pricing jointly with allocation;
- replace legal review of eligibility/netting/fungibility;
- execute, book, or settle recommendations;
- prove causal economic uplift from historical associations; or
- remove the need for human review of exceptional corporate actions and data conflicts.

The LP is globally optimal only for its stated linear assumptions. A more elaborate model can be less
useful if its inputs are not point-in-time, calibrated, and explainable.

---

## 15. Conclusion

Inventory optimization for securities lending is best treated as a constrained, point-in-time
resource-allocation problem rather than a fee ranking exercise. The proposed design begins with the
simplest formulation that captures the essential accounting and economics: post-state route
quantities, exact inventory balances, elasticity-adjusted demand, transition costs, and policy
constraints in a sparse LP.

That baseline creates a trustworthy modular capability inside the existing QR Haven platform for
what-if trades, Bloomberg-enriched security/event and liquidity context, expected activity, agency
owner allocation, prime inventory sourcing, discrete operating rules, robust downside control,
multi-period settlement, and approved inventory transformations. Just as importantly, the software
architecture keeps the optimizer portable and auditable through a one-way platform adapter,
immutable contracts, component registries, solver isolation, independent verification, and complete
attribution.

The project's value should ultimately be judged by verified operational and realized economic
outcomes—not the sophistication of the solver. Correct balances, credible information timing, and
transparent decisions are the foundation on which every extension depends.

---

## References

1. Gene D'Avolio, “The Market for Borrowing Stock,” *Journal of Financial Economics*, 66(2–3),
   271–306, 2002. [DOI](https://doi.org/10.1016/S0304-405X(02)00206-4).
2. Darrell Duffie, Nicolae Gârleanu, and Lasse Heje Pedersen, “Securities Lending, Shorting, and
   Pricing,” *Journal of Financial Economics*, 66(2–3), 307–339, 2002.
   [DOI](https://doi.org/10.1016/S0304-405X(02)00226-X).
3. Adam C. Kolasinski, Adam V. Reed, and Matthew C. Ringgenberg, “A Multiple Lender Approach to
   Understanding Supply and Search in the Equity Lending Market,” *Journal of Finance*, 68(2),
   559–595, 2013. [DOI](https://doi.org/10.1111/jofi.12007).
4. HiGHS project, “High-performance software for large-scale sparse LP, MIP, and QP models.”
   [Project documentation](https://highs.dev/). See also Q. Huangfu and J. A. J. Hall,
   “Parallelizing the Dual Revised Simplex Method,” *Mathematical Programming Computation*, 10,
   119–142, 2018. [DOI](https://doi.org/10.1007/s12532-017-0130-5).
5. R. Tyrrell Rockafellar and Stanislav Uryasev, “Optimization of Conditional Value-at-Risk,”
   *Journal of Risk*, 2(3), 21–41, 2000.
   [DOI](https://doi.org/10.21314/JOR.2000.038).
6. Dimitris Bertsimas and Melvyn Sim, “The Price of Robustness,” *Operations Research*, 52(1),
   35–53, 2004. [Author-hosted paper](https://www.mit.edu/~dbertsim/papers/melvyn/The-Price-Of-Robustness-OR52.pdf).
7. Bloomberg, [Enterprise Data Catalog](https://professional.bloomberg.com/products/data/enterprise-catalog/).
8. Bloomberg, [Reference Data](https://professional.bloomberg.com/products/data/enterprise-catalog/reference/).
9. Bloomberg, [Event-Driven Feeds](https://professional.bloomberg.com/products/data/enterprise-catalog/event-driven-feeds/).
10. Bloomberg, [Real-Time Market Data Feed](https://professional.bloomberg.com/products/data/enterprise-catalog/real-time-data-feed/).
11. Bloomberg, [Funds Data](https://professional.bloomberg.com/products/data/enterprise-catalog/funds/).
12. Bloomberg, [Liquidity Assessment](https://professional.bloomberg.com/products/risk/lqa/).
13. Basel Committee on Banking Supervision, [Counterparty Credit Risk Management Guidelines](https://www.bis.org/committees/bcbs/basel-consolidated-guidelines/module/cri/40),
    including eligible-collateral, haircut, margin-delivery, and substitution considerations for
    securities-financing transactions.
14. Committee on Payment and Settlement Systems, [Securities Lending Transactions: Market Development and Implications](https://www.bis.org/publ/cpss32.pdf),
    Bank for International Settlements, 1999.
15. Office of the Comptroller of the Currency, [Comptroller's Handbook: Custody Services](https://occ.treas.gov/publications-and-resources/publications/comptrollers-handbook/files/custody-services/pub-ch-custody-services.pdf),
    securities-lending program, borrower-selection, customer-guideline, collateral, and
    indemnification considerations.
16. Bank for International Settlements, [The prime broker–hedge fund nexus: recent evolution and implications for bank risks](https://www.bis.org/publications/prime-broker8211hedge-fund-nexus-recent-evolution-and-implications-bank-risks),
    2024.

The Bloomberg references describe broad product categories, not guaranteed field-level entitlement
for a particular deployment. Field availability, permitted use, delivery, retention, and
redistribution must be confirmed under the firm's agreements.
